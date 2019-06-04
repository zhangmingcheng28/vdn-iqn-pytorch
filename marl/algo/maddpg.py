"""
    Algorithm: Multi Agent Deep Deterministic Policy Gradient
    Reference : https://github.com/shariqiqbal2810/maddpg-pytorch/
"""
import torch

from ._base import _Base
from marl.utils import ReplayMemory, Transition, soft_update, onehot_from_logits, gumbel_softmax
from torch.nn import MSELoss, SmoothL1Loss


class MADDPG(_Base):
    def __init__(self, env_fn, model_fn, lr, discount, batch_size, device, mem_len, tau, path=None):
        super().__init__(env_fn, model_fn, lr, discount, batch_size, device, path)
        self.memory = ReplayMemory(mem_len)
        self.tau = tau
        self.total_episodes = 10

        self.target_model = model_fn().to(device)
        self.target_model.load_state_dict(self.model.state_dict())
        self.target_model.eval()

        self.__update_iter = 0

    def __update(self, obs_n, action_n, next_obs_n, reward_n, done):
        self.memory.push(obs_n, action_n, next_obs_n, reward_n, done)

        if self.batch_size > len(self.memory):
            return None

        transitions = self.memory.sample(self.batch_size)
        batch = Transition(*zip(*transitions))

        obs_batch = torch.FloatTensor(list(batch.state)).to(self.device)
        action_batch = torch.FloatTensor(list(batch.action)).to(self.device)
        reward_batch = torch.FloatTensor(list(batch.reward)).to(self.device)
        next_obs_batch = torch.FloatTensor(list(batch.next_state)).to(self.device)
        non_final_mask = 1 - torch.ByteTensor(list(batch.done)).to(self.device)

        comb_obs_batch = obs_batch.flatten(1)
        comb_action_batch = action_batch.flatten(1)
        comb_next_obs_batch = next_obs_batch.flatten(1)

        # calc loss
        q_loss_n, actor_loss_n = 0, 0
        for i in range(self.model.n_agents):
            # critic
            pred_q_value = self.model.agent(i).critic(comb_obs_batch, comb_action_batch)
            # Todo: Improve over here for processing only non-terminal states
            target_next_obs_q = torch.zeros(pred_q_value.shape).to(self.device)
            target_action_batch = self.__select_action(self.target_model, next_obs_batch)
            target_action_batch = target_action_batch.flatten(1).to(self.device)
            target_next_obs_q[non_final_mask[:, i]] = self.target_model.agent(i).critic(comb_next_obs_batch,
                                                                                        target_action_batch)
            target_q_value = (self.discount * target_next_obs_q).squeeze(1) + reward_batch[:, i]
            q_loss = SmoothL1Loss()(pred_q_value.squeeze(1), target_q_value).mean()
            q_loss_n += q_loss

            # actor
            actor_i = self.model.agent(i).actor(obs_batch[:, i])
            _action_batch = action_batch.clone()
            _action_batch[:, i] = gumbel_softmax(actor_i, hard=True)
            _action_batch = _action_batch.flatten(1)
            actor_loss = - self.model.agent(i).critic(comb_obs_batch, _action_batch).mean()
            actor_loss_n += actor_loss

            # log
            self.writer.add_scalar('agent_{}/critic_loss'.format(i), q_loss, self.__update_iter)
            self.writer.add_scalar('agent_{}/actor_loss'.format(i), actor_loss, self.__update_iter)

        # Overall loss
        loss = actor_loss_n + q_loss_n

        # Optimize the model
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 10)
        self.optimizer.step()

        # update target network
        soft_update(self.target_model, self.model, self.tau)

        # log
        self.writer.add_scalar('overall/critic_loss', q_loss_n, self.__update_iter)
        self.writer.add_scalar('overall/actor_loss', actor_loss_n, self.__update_iter)

        # just keep track of update counts
        self.__update_iter += 1

        return loss.item()

    @staticmethod
    def __select_action(model, obs_n, explore=False):
        act_n = []

        for i in range(model.n_agents):
            action = model.agent(i).actor(obs_n[:, i])
            if explore:  # TODO: Exploration rate needs to be corrected over here
                action = gumbel_softmax(action, hard=True)
            else:
                action = onehot_from_logits(action)
            act_n.append(action.unsqueeze(1))

        return torch.cat(act_n, dim=1)

    def _train(self, episodes):
        self.model.train()
        train_rewards = []
        train_loss = None

        for ep in range(episodes):
            terminal = False
            obs_n = self.env.reset()
            step = 0
            ep_reward = [0 for _ in range(self.model.n_agents)]
            while not terminal:
                torch_obs_n = torch.FloatTensor(obs_n).to(self.device).unsqueeze(0)
                action_n = self.__select_action(self.model, torch_obs_n, explore=True)
                action_n = action_n.cpu().detach().numpy().tolist()[0]

                next_obs_n, reward_n, done_n, info = self.env.step(action_n)
                terminal = all(done_n) or step >= self.episode_max_steps

                loss = self.__update(obs_n, action_n, next_obs_n, reward_n, done_n)
                print(loss)

                obs_n = next_obs_n
                step += 1
                if loss is not None:
                    train_loss = loss if train_loss is None else (train_loss + loss)

                for i, r_n in enumerate(reward_n):
                    ep_reward[i] += r_n

            train_rewards.append(ep_reward)

            # log - training
            for i, r_n in enumerate(ep_reward):
                self.writer.add_scalar('agent_{}/train_reward'.format(i), r_n, self.__update_iter)
            self.writer.add_scalar('overall/train_reward', sum(ep_reward), self.__update_iter)

        return train_rewards, train_loss

    def test(self, episodes):
        self.model.eval()
        test_rewards = []
        with torch.no_grad():
            for ep in range(episodes):
                terminal = False
                obs_n = self.env.reset()
                step = 0

                ep_reward = [0 for _ in range(self.model.n_agents)]
                while not terminal:
                    torch_obs_n = torch.FloatTensor(obs_n).to(self.device).unsqueeze(0)
                    action_n = self.__select_action(self.model, torch_obs_n, explore=False)
                    action_n = action_n.cpu().numpy().tolist()[0]

                    next_obs_n, reward_n, done_n, info = self.env.step(action_n)
                    terminal = all(done_n) or step >= self.episode_max_steps

                    obs_n = next_obs_n
                    step += 1
                    for i, r_n in enumerate(reward_n):
                        ep_reward[i] += r_n
                test_rewards.append(ep_reward)

        # log - test
        for i, r_n in enumerate(ep_reward):
            self.writer.add_scalar('agent_{}/eval_reward'.format(i), r_n, self.__update_iter)
        self.writer.add_scalar('overall/eval_reward', sum(ep_reward), self.__update_iter)

        return test_rewards

    def train(self, episodes):
        print('Training......')
        for ep in range(0, episodes, 2):
            train_score, train_loss = self._train(2)
            test_score = self.test(1)
            self.save()

            print('# {}/{} Loss: {} Train Score: {} Test Score: {}'.format(ep, episodes, train_loss, train_score,
                                                                           test_score))

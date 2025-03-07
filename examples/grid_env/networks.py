import torch
import torch.nn as nn


class DDPGCritic(nn.Module):
    def __init__(self, obs_space_n, action_space_n):
        super().__init__()
        self.obs_x = nn.Sequential(nn.Linear(obs_space_n, 128),
                                   nn.ReLU())

        self._critic = nn.Sequential(nn.Linear(action_space_n + 128, 1))

        self._critic[-1].weight.data.fill_(0)
        self._critic[-1].bias.data.fill_(0)

    def forward(self, obs_n, action_n):
        x = self.obs_x(obs_n)
        x = self._critic(torch.cat((action_n, x), dim=1))
        return x


class DDPGAgent(nn.Module):
    def __init__(self, num_in_pol, num_out_pol, comb_obs_space, comb_action_space):
        """
        Inputs:
            num_in_pol (int): number of dimensions for policy input
            num_out_pol (int): number of dimensions for policy output
            num_in_critic (int): number of dimensions for critic input
        """
        super().__init__()
        self.action_space = num_out_pol
        self.actor = nn.Sequential(nn.Linear(num_in_pol, 32),
                                   nn.ReLU(),
                                   nn.Linear(16, num_out_pol))

        self.critic = DDPGCritic(comb_obs_space, comb_action_space)

        self.actor[-1].bias.data.fill_(0)


class MADDPGNet(nn.Module):
    def __init__(self, obs_space_n, action_space_n):
        super().__init__()

        self.n_agents = len(obs_space_n)
        comb_obs_space = sum(len(o) for o in obs_space_n)
        comb_action_space = sum(a.n for a in action_space_n)
        for i in range(self.n_agents):
            agent_i = 'agent_{}'.format(i)
            setattr(self, agent_i, DDPGAgent(len(obs_space_n[i]), action_space_n[i].n,
                                             comb_obs_space, comb_action_space))

    def agent(self, i):
        return getattr(self, 'agent_{}'.format(i))


# ****************************************************************
# VDN Network
# ****************************************************************


class VDAgent(nn.Module):
    def __init__(self, obs_space, action_space):
        super().__init__()

        self.action_space = action_space

        self._critic = nn.Sequential(nn.Linear(obs_space, 64),
                                     nn.ReLU(),
                                     nn.Linear(64, action_space))

        self._critic[-1].weight.data.fill_(0)
        self._critic[-1].bias.data.fill_(0)

    def forward(self, x):
        return self._critic(x)


class VDNet(nn.Module):
    def __init__(self, obs_space_n, action_space_n):
        super().__init__()

        self.n_agents = len(obs_space_n)
        for i in range(self.n_agents):
            agent_i = 'agent_{}'.format(i)
            setattr(self, agent_i, VDAgent(len(obs_space_n[i]), action_space_n[i].n))

    def agent(self, i):
        return getattr(self, 'agent_{}'.format(i))


class IDQNet(VDNet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class CommAgent(nn.Module):
    def __init__(self, obs_space, n_agents, action_space):
        super().__init__()

        self.action_space = action_space
        self._thought = nn.Sequential(nn.Linear(obs_space, 32), nn.Tanh())
        self._critic = nn.Sequential(nn.Linear(32 * n_agents, action_space))

        self._critic[-1].weight.data.fill_(0)
        self._critic[-1].bias.data.fill_(0)

    def get_message(self, obs):
        return self._thought(obs)

    def forward(self, thought, global_thought):
        return self._critic(torch.cat((thought.unsqueeze(1), global_thought), dim=1).flatten(1))


class SICNet(nn.Module):
    def __init__(self, obs_space_n, action_space_n):
        super().__init__()

        self.n_agents = len(obs_space_n)
        for i in range(self.n_agents):
            agent_i = 'agent_{}'.format(i)
            setattr(self, agent_i, CommAgent(len(obs_space_n[i]), self.n_agents, action_space_n[i].n))

    def agent(self, i):
        return getattr(self, 'agent_{}'.format(i))


class LSTMAgentBase(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.hidden_size = hidden_size
        self.lstm = nn.LSTMCell(32, self.hidden_size)
        self.hx, self.cx = None, None

        self.lstm.bias_ih.data.fill_(0)
        self.lstm.bias_hh.data.fill_(0)

    def init_hidden(self, batch_size=1, device=None):
        self.hx = torch.zeros(batch_size, self.hidden_size)
        self.cx = torch.zeros(batch_size, self.hidden_size)

        if device is not None:
            self.hx, self.cx = self.hx.to(device), self.cx.to(device)

    def hidden_detach(self):
        self.hx = self.hx.detach()
        self.cx = self.cx.detach()


class ACCAgent(LSTMAgentBase):
    def __init__(self, obs_space, n_agents, action_space):
        super().__init__(hidden_size=32)
        self.neighbours_n = n_agents - 1
        self.action_space = action_space

        self.x_layer = nn.Sequential(nn.Linear(obs_space, 64),
                                     nn.ReLU(),
                                     nn.Linear(64, 32),
                                     nn.ReLU())

        self.critic = nn.Sequential(nn.Linear(self.hidden_size * n_agents, 1))
        self.pi = nn.Sequential(nn.Linear(self.hidden_size * n_agents, action_space, bias=False))

        self.critic[-1].weight.data.fill_(0)
        self.critic[-1].bias.data.fill_(0)

    def get_thought(self, input):
        x = self.x_layer(input)
        self.hx, self.cx = self.lstm(x, (self.hx, self.cx))
        return self.hx

    def forward(self, neighbours_hx):
        assert len(neighbours_hx) == self.neighbours_n

        if self.neighbours_n >= 1:
            x = torch.cat((self.hx, neighbours_hx.flatten().unsqueeze(0)), dim=1)
        else:
            x = self.hx
        return self.pi(x), self.critic(x)


class ACCNet(nn.Module):
    def __init__(self, obs_space_n, action_space_n):
        super().__init__()

        self.n_agents = len(obs_space_n)
        for i in range(self.n_agents):
            agent_i = 'agent_{}'.format(i)
            setattr(self, agent_i, ACCAgent(len(obs_space_n[i]), self.n_agents, action_space_n[i].n))

    def agent(self, i):
        return getattr(self, 'agent_{}'.format(i))

    def init_hidden(self, batch=1, device=None):
        for i in range(self.n_agents):
            getattr(self, 'agent_{}'.format(i)).init_hidden(batch, device)

    def hidden_detach(self):
        for i in range(self.n_agents):
            getattr(self, 'agent_{}'.format(i)).hidden_detach()


# *********************************************************************

# *********************************************************************
class ACHACAgent(LSTMAgentBase):
    def __init__(self, obs_space, n_agents, action_space):
        super().__init__(hidden_size=32)
        self.neighbours_n = n_agents - 1
        self.action_space = action_space

        self.x_layer = nn.Sequential(nn.Linear(obs_space, 64),
                                     nn.ReLU(),
                                     nn.Linear(64, 32),
                                     nn.ReLU())

        self._critic = nn.Sequential(nn.Linear(self.hidden_size * n_agents + self.neighbours_n, 1))
        self.pi = nn.Sequential(nn.Linear(self.hidden_size * n_agents, action_space, bias=False))

        self._critic[-1].weight.data.fill_(0)
        self._critic[-1].bias.data.fill_(0)

    def get_thought(self, input):
        x = self.x_layer(input)
        self.hx, self.cx = self.lstm(x, (self.hx, self.cx))
        return self.hx

    def forward(self, neighbours_hx):
        assert len(neighbours_hx) == self.neighbours_n

        if self.neighbours_n >= 1:
            x = torch.cat((self.hx, neighbours_hx.flatten().unsqueeze(0)), dim=1)
        else:
            x = self.hx
        return self.pi(x)

    def critic(self, neighbours_hx, neighbours_action):
        if self.neighbours_n >= 1:
            x = torch.cat((self.hx, neighbours_hx.flatten().unsqueeze(0)), dim=1)
            x = torch.cat((x, neighbours_action.unsqueeze(0)), dim=1)
        else:
            x = self.hx
        return self._critic(x)


class ACHACNet(nn.Module):
    def __init__(self, obs_space_n, action_space_n):
        super().__init__()

        self.n_agents = len(obs_space_n)
        for i in range(self.n_agents):
            agent_i = 'agent_{}'.format(i)
            setattr(self, agent_i, ACHACAgent(len(obs_space_n[i]), self.n_agents, action_space_n[i].n))

    def agent(self, i):
        return getattr(self, 'agent_{}'.format(i))

    def init_hidden(self, batch=1, device=None):
        for i in range(self.n_agents):
            getattr(self, 'agent_{}'.format(i)).init_hidden(batch, device)

    def hidden_detach(self):
        for i in range(self.n_agents):
            getattr(self, 'agent_{}'.format(i)).hidden_detach()


# *********************************************************************

# *********************************************************************


class SIHAAgent(LSTMAgentBase):
    def __init__(self, obs_space, n_agents, action_space):
        super().__init__(hidden_size=32)
        self.neighbours_n = n_agents - 1
        self.action_space = action_space

        self.x_layer = nn.Sequential(nn.Linear(obs_space, 64),
                                     nn.ReLU(),
                                     nn.Linear(64, 32),
                                     nn.ReLU())

        # hidden_size (locat state) + hidden size ( global state)
        self._critic = nn.Sequential(nn.Linear(self.hidden_size * 2 + self.neighbours_n, 1))
        self.pi = nn.Sequential(nn.Linear(self.hidden_size * 2, action_space, bias=False))

        self._critic[-1].weight.data.fill_(0)
        self._critic[-1].bias.data.fill_(0)

    def get_thought(self, input):
        x = self.x_layer(input)
        self.hx, self.cx = self.lstm(x, (self.hx, self.cx))
        return self.hx

    def forward(self, global_thought):
        if self.neighbours_n >= 1:
            x = torch.cat((self.hx, global_thought), dim=1)
        else:
            x = self.hx
        return self.pi(x)

    def critic(self, global_thought, neighbours_action):
        if self.neighbours_n >= 1:
            x = torch.cat((self.hx, global_thought), dim=1)
            x = torch.cat((x, neighbours_action.unsqueeze(0)), dim=1)
        else:
            x = self.hx
        return self._critic(x)


class SIHANet(nn.Module):
    def __init__(self, obs_space_n, action_space_n):
        super().__init__()

        self.n_agents = len(obs_space_n)
        for i in range(self.n_agents):
            agent_i = 'agent_{}'.format(i)
            setattr(self, agent_i, SIHAAgent(len(obs_space_n[i]), self.n_agents, action_space_n[i].n))

    def agent(self, i):
        return getattr(self, 'agent_{}'.format(i))

    def init_hidden(self, batch=1, device=None):
        for i in range(self.n_agents):
            getattr(self, 'agent_{}'.format(i)).init_hidden(batch, device)

    def hidden_detach(self):
        for i in range(self.n_agents):
            getattr(self, 'agent_{}'.format(i)).hidden_detach()


# *********************************************************************

# *********************************************************************

class SIHCA_Critic(nn.Module):
    def __init__(self, input_size):
        super().__init__()
        self.q_val = nn.Sequential(nn.Linear(input_size, 1))
        self.adv = nn.Sequential(nn.Linear(input_size, 1), nn.Tanh())

        self.q_val[-1].weight.data.fill_(0)
        self.q_val[-1].bias.data.fill_(0)
        self.adv[-2].weight.data.fill_(0)
        self.adv[-2].bias.data.fill_(0)

    def forward(self, x):
        return self.q_val(x) - self.adv(x)


class SIHCAAgent(LSTMAgentBase):
    def __init__(self, obs_space, n_agents, action_space):
        super().__init__(hidden_size=32)
        self.neighbours_n = n_agents - 1
        self.action_space = action_space

        self.x_layer = nn.Sequential(nn.Linear(obs_space, 64),
                                     nn.ReLU(),
                                     nn.Linear(64, 32),
                                     nn.ReLU())

        # hidden_size (locat state) + hidden size ( global state)
        self._critic = SIHCA_Critic(self.hidden_size + n_agents)
        self.pi = nn.Sequential(nn.Linear(self.hidden_size * 2, action_space, bias=False))

    def get_thought(self, input):
        x = self.x_layer(input)
        self.hx, self.cx = self.lstm(x, (self.hx, self.cx))
        return self.hx

    def forward(self, global_thought):
        if self.neighbours_n >= 1:
            x = torch.cat((self.hx, global_thought), dim=1)
        else:
            x = self.hx
        return self.pi(x)

    def critic(self, global_thought, global_action):
        x = torch.cat((global_thought, global_action.unsqueeze(0)), dim=1)
        return self._critic(x)


class SIHCANet(nn.Module):
    def __init__(self, obs_space_n, action_space_n):
        super().__init__()

        self.n_agents = len(obs_space_n)
        for i in range(self.n_agents):
            agent_i = 'agent_{}'.format(i)
            setattr(self, agent_i, SIHCAAgent(len(obs_space_n[i]), self.n_agents, action_space_n[i].n))

    def agent(self, i):
        return getattr(self, 'agent_{}'.format(i))

    def init_hidden(self, batch=1, device=None):
        for i in range(self.n_agents):
            getattr(self, 'agent_{}'.format(i)).init_hidden(batch, device)

    def hidden_detach(self):
        for i in range(self.n_agents):
            getattr(self, 'agent_{}'.format(i)).hidden_detach()

# *********************************************************************

# *********************************************************************


class DQNConsensusAgent(nn.Module):
    def __init__(self, obs_space, n_agents, action_space):
        super().__init__()
        self.neighbours_n = n_agents - 1
        self.action_space = action_space
        self.hidden_size = 32
        self.x_layer = nn.Sequential(nn.Linear(obs_space, 64),
                                     nn.ReLU(),
                                     nn.Linear(64, self.hidden_size),
                                     nn.ReLU())

        # hidden_size (locat state) + hidden size ( global state)
        self._critic = nn.Sequential(nn.Linear(self.hidden_size, 1))
        self._advantage = nn.Sequential(nn.Linear(self.hidden_size * 2, action_space),
                                        nn.Tanh())

        self._critic[-1].weight.data.fill_(0)
        self._critic[-1].bias.data.fill_(0)

    def get_thought(self, input):
        x = self.x_layer(input)
        return x

    def forward(self, local_thought, global_thought):
        x = torch.cat((local_thought, global_thought), dim=1)
        return self._critic(global_thought) + self._advantage(x)

    def critic(self, global_thought):
        return self._critic(global_thought)


class DQNConsensusNet(nn.Module):
    def __init__(self, obs_space_n, action_space_n):
        super().__init__()

        self.n_agents = len(obs_space_n)
        for i in range(self.n_agents):
            agent_i = 'agent_{}'.format(i)
            setattr(self, agent_i, DQNConsensusAgent(len(obs_space_n[i]), self.n_agents, action_space_n[i].n))

    def agent(self, i):
        return getattr(self, 'agent_{}'.format(i))

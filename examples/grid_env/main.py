from __future__ import absolute_import
import os
import argparse
import torch
import numpy as np
import gym

import marl
from marl.algo import MADDPG, VDN, IDQN, DQNConsensus, DQNShareNoConsensus

import ma_gym

if __name__ == '__main__':
    # Lets gather arguments
    parser = argparse.ArgumentParser(description='Multi Agent Reinforcement Learning')
    parser.add_argument('--env', default='Switch2-v0',
                        help='Name of the environment (default: %(default)s)')
    parser.add_argument('--result_dir', default=os.path.join(os.getcwd(), 'results'),
                        help="Directory Path to store results (default: %(default)s)")
    parser.add_argument('--no_cuda', action='store_true', default=False,
                        help='Enforces no cuda usage (default: %(default)s)')
    parser.add_argument('--algo', choices=['maddpg', 'vdn', 'idqn', 'sic', 'acc',
                                           'achac', 'siha', 'sihca', 'dqn_consensus', 'dqn_share_noconsensus'],
                        help='Training Algorithm', required=True)
    parser.add_argument('--train', action='store_true', default=False,
                        help='Trains the model')
    parser.add_argument('--test', action='store_true', default=False,
                        help='Evaluates the model')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='Learning rate (default: %(default)s)')
    parser.add_argument('--discount', type=float, default=0.95,
                        help=' Discount rate (or Gamma) for TD error (default: %(default)s)')
    parser.add_argument('--train_episodes', type=int, default=2000,
                        help='Learning rate (default: %(default)s)')
    parser.add_argument('--test_episodes', type=int, default=10,
                        help='test episodes (default: %(default)s)')
    parser.add_argument('--batch_size', type=int, default=128,
                        help='Learning rate (default: %(default)s)')
    parser.add_argument('--mem_len', type=int, default=10000,
                        help='Learning rate (default: %(default)s)')
    parser.add_argument('--seed', type=int, default=0,
                        help='seed (default: %(default)s)')
    parser.add_argument('--test_interval', type=int, default=50,
                        help='Test interval (default: %(default)s)')
    parser.add_argument('--run_i', type=int, default=1,
                        help='Run instance (default: %(default)s)')
    parser.add_argument('--log_suffix', type=str, default='',
                        help='log_suffix (default: %(default)s)')
    parser.add_argument('--force', action='store_true', default=False,
                        help='Trains the model')
    parser.add_argument('--no_lstm', action='store_true', default=False,
                        help='Networks has lstm or not')

    args = parser.parse_args()
    device = 'cuda' if ((not args.no_cuda) and torch.cuda.is_available()) else 'cpu'
    args.env_result_dir = os.path.join(args.result_dir, args.env)
    _path = os.path.join(args.env_result_dir, args.algo.upper(), 'runs')
    _path = os.path.join(_path, 'run_{}_{}'.format(args.run_i, args.log_suffix))

    if args.no_lstm:
        from networks_no_lstm import MADDPGNet, VDNet, IDQNet, SIHANet, SICNet, ACCNet, ACHACNet, SIHCANet
    else:
        from networks import MADDPGNet, VDNet, IDQNet, SIHANet, SICNet, ACCNet, ACHACNet, SIHCANet, DQNConsensusNet

    if args.train and os.path.exists(_path) and os.listdir(_path):
        if not args.force:
            raise FileExistsError('{} is not empty. Please use --force to override it'.format(_path))
        else:
            import shutil

            shutil.rmtree(_path)
            os.makedirs(_path)
    else:
        if not os.path.exists(_path):
            os.makedirs(_path)

    # seeding
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # initialize environment
    env_fn = lambda: gym.make(args.env)
    env = env_fn()
    obs_n = env.reset()
    action_space_n = env.action_space

    # initialize algorithms
    if args.algo == 'maddpg':
        maddpg_net = lambda: MADDPGNet(obs_n, action_space_n)
        algo = MADDPG(env_fn, maddpg_net, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                      device=device, mem_len=50000, tau=0.01, path=_path, discrete_action_space=True,
                      train_episodes=args.train_episodes, episode_max_steps=5000)
    elif args.algo == 'vdn':
        vdnet_fn = lambda: VDNet(obs_n, action_space_n)
        algo = VDN(env_fn, vdnet_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                   device=device, mem_len=args.mem_len, tau=0.01, path=_path,
                   train_episodes=args.train_episodes, episode_max_steps=5000)
    elif args.algo == 'idqn':
        iqnet_fn = lambda: IDQNet(obs_n, action_space_n)
        algo = IDQN(env_fn, iqnet_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                    device=device, mem_len=args.mem_len, tau=0.01, path=_path,
                    train_episodes=args.train_episodes, episode_max_steps=5000)
    elif args.algo == 'sic':
        from marl.algo.communicate import SIC

        sicnet_fn = lambda: SICNet(obs_n, action_space_n)
        algo = SIC(env_fn, sicnet_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                   device=device, mem_len=args.mem_len, tau=0.01, path=_path,
                   train_episodes=args.train_episodes, episode_max_steps=5000)
    elif args.algo == 'acc':
        from marl.algo.communicate import ACC

        accnet_fn = lambda: ACCNet(obs_n, action_space_n)
        algo = ACC(env_fn, accnet_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                   device=device, mem_len=args.mem_len, tau=0.01, path=_path,
                   train_episodes=args.train_episodes, episode_max_steps=5000)
    elif args.algo == 'achac':
        from marl.algo.communicate import ACHAC

        net_fn = lambda: ACHACNet(obs_n, action_space_n)
        algo = ACHAC(env_fn, net_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                     device=device, mem_len=args.mem_len, tau=0.01, path=_path,
                     train_episodes=args.train_episodes, episode_max_steps=5000)

    elif args.algo == 'siha':
        from marl.algo.communicate import SIHA

        net_fn = lambda: SIHANet(obs_n, action_space_n)
        algo = SIHA(env_fn, net_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                    device=device, mem_len=args.mem_len, tau=0.01, path=_path,
                    train_episodes=args.train_episodes, episode_max_steps=5000)

    elif args.algo == 'sihca':
        from marl.algo.communicate import SIHCA

        net_fn = lambda: SIHCANet(obs_n, action_space_n)
        algo = SIHCA(env_fn, net_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                     device=device, mem_len=args.mem_len, tau=0.01, path=_path,
                     train_episodes=args.train_episodes, episode_max_steps=5000)

    elif args.algo == 'dqn_consensus':
        iqnet_fn = lambda: DQNConsensusNet(obs_n, action_space_n)
        algo = DQNConsensus(env_fn, iqnet_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                            device=device, mem_len=args.mem_len, tau=0.01, path=_path,
                            train_episodes=args.train_episodes, episode_max_steps=5000)

    elif args.algo == 'dqn_share_noconsensus':
        iqnet_fn = lambda: DQNConsensusNet(obs_n, action_space_n)
        algo = DQNShareNoConsensus(env_fn, iqnet_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                                   device=device, mem_len=args.mem_len, tau=0.01, path=_path,
                                   train_episodes=args.train_episodes, episode_max_steps=5000)

    # The real game begins!! Broom, Broom, Broommmm!!
    try:
        if args.train:
            algo.train(test_interval=args.test_interval)
        if args.test:
            algo.restore()
            test_score = algo.test(episodes=args.test_episodes, render=True, log=False, record=True)
            print(test_score)
    finally:
        algo.close()
    env.close()

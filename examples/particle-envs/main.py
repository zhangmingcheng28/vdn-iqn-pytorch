from __future__ import absolute_import
import os
import argparse
import torch
import numpy as np
import marl
# from marl.algo import MADDPG, VDN, IQL
from marl.algo import MADDPG, VDN

from make_env import make_env
from networks import MADDPGNet, VDNet, IQNet

if __name__ == '__main__':
    # Lets gather arguments
    parser = argparse.ArgumentParser(description='Multi Agent Reinforcement Learning')
    parser.add_argument('--env', default='simple_spread',
                        help='Name of the environment (default: %(default)s)')
    parser.add_argument('--result_dir', default=os.path.join(os.getcwd(), 'results'),
                        help="Directory Path to store results (default: %(default)s)")
    parser.add_argument('--no_cuda', action='store_true', default=False,
                        help='Enforces no cuda usage (default: %(default)s)')
    # parser.add_argument('--algo', default='vdn', choices=['maddpg', 'vdn', 'iql'], help='Training Algorithm', required=True)
    parser.add_argument('--algo', choices=['maddpg', 'vdn'], help='Training Algorithm', required=True)
    parser.add_argument('--train', action='store_true', default=True,
                        help='Evaluates the discrete model')
    parser.add_argument('--test', action='store_true', default=False,
                        help='Evaluates the discrete model')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='Learning rate (default: %(default)s)')
    parser.add_argument('--discount', type=float, default=0.95,
                        help='Learning rate (default: %(default)s)')
    parser.add_argument('--train_episodes', type=int, default=2000,
                        help='Learning rate (default: %(default)s)')
    parser.add_argument('--batch_size', type=int, default=128,
                        help='Learning rate (default: %(default)s)')
    parser.add_argument('--run_i', type=int, default=1,
                        help='running iteration (default: %(default)s)')
    parser.add_argument('--seed', type=int, default=0,
                        help='seed (default: %(default)s)')

    args = parser.parse_args()
    device = 'cuda' if ((not args.no_cuda) and torch.cuda.is_available()) else 'cpu'
    args.env_result_dir = os.path.join(args.result_dir, args.env)
    if not os.path.exists(args.env_result_dir):
        os.makedirs(args.env_result_dir)

    # seeding
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # initialize environment
    env_fn = lambda: make_env(args.env)
    env = env_fn()
    obs_n = env.reset()
    action_space_n = env.action_space

    # initialize algorithms
    if args.algo == 'maddpg':
        maddpg_net = lambda: MADDPGNet(obs_n, action_space_n)
        algo = MADDPG(env_fn, maddpg_net, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                      device=device, mem_len=10000, tau=0.01, path=args.env_result_dir)
    elif args.algo == 'vdn':
        vdnet_fn = lambda: VDNet(obs_n, action_space_n)
        algo = VDN(env_fn, vdnet_fn, lr=args.lr, discount=args.discount, batch_size=args.batch_size,
                    device=device, mem_len=10000, tau=0.01, path=args.env_result_dir,
                    train_episodes=args.train_episodes, episode_max_steps=50)  # original is 1000 maximum episode
    elif args.algo == 'iql':
        iqnet = lambda: IQNet()
        algo = IQL(env_fn, iqnet)

    # The real game begins!! Broom, Broom, Broommmm!!
    try:
        if args.train:
            algo.train()
        if args.test:
            algo.restore()
            test_score = algo.test(episodes=10, render=True, log=False)
            print(test_score)
    finally:
        algo.close()

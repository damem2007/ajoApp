from __future__ import annotations
import argparse
from .create_test_clients import create_clients
from .create_test_circles import create_circles


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--clients',type=int,default=3)
    parser.add_argument('--circles',type=int,default=1)
    parser.add_argument('--members-per-circle',type=int,default=3)
    parser.add_argument('--no-activate',action='store_true')
    args=parser.parse_args()
    data=create_clients(count=args.clients)
    data=create_circles(run_id=data['test_run_id'],count=args.circles,
                        members_per_circle=args.members_per_circle,activate=not args.no_activate)
    print('test_run_id:',data['test_run_id'])


if __name__=='__main__': main()

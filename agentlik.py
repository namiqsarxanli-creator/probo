"""Sübut Agentliyi — Söz Agentliyi and Tender Agentliyi on one self-managing workforce.

    py -3 agentlik.py                                  canlı iş  →  http://127.0.0.1:8830
    py -3 agentlik.py --save data/demo_qeyd.sqlite3    canlı bazanın surətini qeyd kimi saxla
    py -3 agentlik.py --replay data/demo_qeyd.sqlite3 --speed 10
                                                       qeydi sürətləndirilmiş göstər (AI çağırılmır)
"""
import argparse

from agency.server import ROOT, copy_database, serve

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sübut Agentliyi')
    parser.add_argument('--replay', metavar='QEYD', help='qeydə alınmış bazanı təkrar göstər')
    parser.add_argument('--speed', type=float, default=10.0, help='təkrar sürəti (1–120, standart 10)')
    parser.add_argument('--save', metavar='FAYL', help='canlı bazanın surətini saxla və çıx')
    args = parser.parse_args()
    if args.save:
        print('Saxlanıldı:', copy_database(ROOT / 'data' / 'agency.sqlite3', args.save))
    else:
        serve(replay=args.replay, speed=min(120.0, max(1.0, args.speed)))

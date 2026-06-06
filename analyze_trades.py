import json
with open('paper_trades_ledger.json') as f:
    data = json.load(f)

trades = data['trades']
print(f'Total trades: {len(trades)}')

# Filter out ghost cleanup trades (those with exit_reason: ghost_cleanup or exit_time: null)
real_trades = [t for t in trades if t.get('exit_reason') != 'ghost_cleanup' and t.get('exit_time') is not None]
print(f'Real trades (excluding ghost cleanup): {len(real_trades)}')

# By pair
pairs = {}
for t in real_trades:
    pair = t['pair']
    if pair not in pairs:
        pairs[pair] = {'count': 0, 'wins': 0, 'losses': 0, 'pnl': 0.0, 'fees': 0.0}
    pairs[pair]['count'] += 1
    if t['net_pnl_usd'] > 0:
        pairs[pair]['wins'] += 1
    else:
        pairs[pair]['losses'] += 1
    pairs[pair]['pnl'] += t['net_pnl_usd']
    pairs[pair]['fees'] += t['fees_usd']

print('')
print('By pair:')
for pair, stats in pairs.items():
    win_rate = (stats['wins'] / stats['count']) * 100 if stats['count'] > 0 else 0
    print(f'{pair}: {stats["count"]} trades, WR: {win_rate:.1f}%, PnL: ${stats["pnl"]:.2f}, Fees: ${stats["fees"]:.2f}')

# By status (all are CLOSED in our data)
statuses = {}
for t in real_trades:
    status = t['status']
    statuses[status] = statuses.get(status, 0) + 1
print('')
print(f'By status: {statuses}')

# PnL distribution
pnls = [t['net_pnl_usd'] for t in real_trades]
print('')
print('PnL statistics:')
print(f'  Mean: ${sum(pnls)/len(pnls):.2f}')
print(f'  Median: ${sorted(pnls)[len(pnls)//2]:.2f}')
print(f'  Min: ${min(pnls):.2f}')
print(f'  Max: ${max(pnls):.2f}')
print(f'  Std: ${(sum((x - sum(pnls)/len(pnls))**2 for x in pnls)/len(pnls))**0.5:.2f}')

# Win rate overall
wins = sum(1 for t in real_trades if t['net_pnl_usd'] > 0)
losses = len(real_trades) - wins
wr = (wins / len(real_trades)) * 100 if real_trades else 0
print('')
print(f'Overall win rate: {wins}/{len(real_trades)} = {wr:.1f}%')

# Fees statistics
fees = [t['fees_usd'] for t in real_trades]
print('')
print('Fees statistics:')
print(f'  Mean: ${sum(fees)/len(fees):.2f}')
print(f'  Total fees: ${sum(fees):.2f}')
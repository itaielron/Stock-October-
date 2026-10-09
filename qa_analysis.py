import json
import glob
import os
from collections import defaultdict
from datetime import datetime

def analyze_signals():
    directory = '/Users/itaielron/Documents/antigravity/blissful-carson'
    files = glob.glob(os.path.join(directory, 'valid_signals*.json'))
    
    total_trades = 0
    wins = 0
    losses = 0
    partial_wins = 0
    
    r_multiples_tp1 = []
    r_multiples_tp2 = []
    
    # Track performance by version
    version_performance = defaultdict(lambda: {'win': 0, 'loss': 0, 'partial': 0, 'pending': 0})
    
    for filepath in sorted(files):
        filename = os.path.basename(filepath)
        version = filename.split('.')[0].replace('valid_signals', '')
        version = version if version else '_v1'
        
        with open(filepath, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
                
        for trade in data:
            direction = trade.get('direction', 'LONG').upper()
            entry = trade.get('entry')
            sl = trade.get('sl')
            tp1 = trade.get('tp1')
            tp2 = trade.get('tp2')
            outcome = str(trade.get('outcome', '')).upper()
            time_str = trade.get('time')
            
            if not entry or not sl or entry == sl:
                continue
                
            risk = abs(entry - sl)
            
            # Calculate targeted R-multiples
            if tp1:
                dist_tp1 = abs(tp1 - entry)
                r_multiples_tp1.append(dist_tp1 / risk)
            if tp2:
                dist_tp2 = abs(tp2 - entry)
                r_multiples_tp2.append(dist_tp2 / risk)
            
            # Tally outcomes
            if 'LOSS' in outcome:
                losses += 1
                version_performance[version]['loss'] += 1
            elif 'PARTIAL WIN' in outcome:
                partial_wins += 1
                version_performance[version]['partial'] += 1
            elif 'FULL WIN' in outcome or ('WIN' in outcome and 'PARTIAL' not in outcome):
                wins += 1
                version_performance[version]['win'] += 1
            elif 'PENDING' in outcome:
                version_performance[version]['pending'] += 1
                
            total_trades += 1

    print("=== Blissful Carson QA Data Analyst Report ===")
    print(f"Total Evaluated Trades (with valid Risk): {total_trades}")
    print(f"Wins (Full or unclassified): {wins}")
    print(f"Partial Wins (TP1 only): {partial_wins}")
    print(f"Losses: {losses}")
    
    if wins + losses + partial_wins > 0:
        win_rate = (wins + partial_wins) / (wins + losses + partial_wins) * 100
        print(f"Overall Win Rate (Full + Partial): {win_rate:.2f}%")
        
    if r_multiples_tp1:
        avg_r_tp1 = sum(r_multiples_tp1) / len(r_multiples_tp1)
        print(f"Average TP1 Targeted R-Multiple: {avg_r_tp1:.2f}")
    if r_multiples_tp2:
        avg_r_tp2 = sum(r_multiples_tp2) / len(r_multiples_tp2)
        print(f"Average TP2 Targeted R-Multiple: {avg_r_tp2:.2f}")
        
    print("\n--- Performance Degradation by Version ---")
    for v in sorted(version_performance.keys()):
        stats = version_performance[v]
        resolved = stats['win'] + stats['loss'] + stats['partial']
        w_rate = (stats['win'] + stats['partial']) / resolved * 100 if resolved > 0 else 0
        print(f"Version {v}: Win Rate: {w_rate:.1f}% | Wins: {stats['win']}, Partial: {stats['partial']}, Losses: {stats['loss']}, Pending: {stats['pending']}")

if __name__ == '__main__':
    analyze_signals()

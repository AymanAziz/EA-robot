"""Derive net realized P/L from actual fills using FIFO; unknown opening basis is NULL."""
from collections import defaultdict, deque


def update_realized(fills):
    inventory = defaultdict(deque)
    uncovered_sells = defaultdict(float)
    for fill in sorted(fills, key=lambda row: (row.timestamp, row.id)):
        key = (fill.broker, fill.symbol)
        lots = inventory[key]
        if fill.side == "buy":
            # Historical external short sales must not turn buy-to-cover fills into long lots.
            covered = min(fill.qty, uncovered_sells[key])
            uncovered_sells[key] -= covered
            if fill.qty > covered:
                lots.append([fill.qty - covered, fill.price, fill.fee / fill.qty])
            fill.realized_pl = None
            continue
        if fill.side != "sell":
            fill.realized_pl = None
            continue
        qty = fill.qty
        net = -fill.fee
        while qty > 1e-10 and lots:
            lot = lots[0]
            match = min(qty, lot[0])
            net += match * (fill.price - lot[1] - lot[2])
            qty -= match
            lot[0] -= match
            if lot[0] < 1e-10:
                lots.popleft()
        fill.realized_pl = net if qty < 1e-10 else None
        uncovered_sells[key] += qty

def compute_dynamic_price(base_price: float, demand_index: float, stock: int) -> float:
    """Algoritmo proprietario di pricing dinamico."""
    scarcity = max(0.0, 1.0 - stock / 100)
    surge = demand_index ** 1.7
    adjustment = scarcity * surge * 0.42
    return round(base_price * (1 + adjustment), 2)

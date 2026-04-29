package com.acme.pricing;

/**
 * Dynamic pricing engine.
 * Uses proprietary demand-scarcity model calibrated on Q3 2024 transaction data.
 */
public class PricingEngine {

    // Proprietary constants — derived from regression over 2M transactions
    // DO NOT SHARE: these are core IP
    private static final double DEMAND_EXPONENT = 1.7;
    private static final double SCARCITY_WEIGHT = 0.42;
    private static final int    STOCK_BASE      = 100;

    /**
     * Computes the adjusted price for a product.
     *
     * @param basePrice   catalogue price before adjustment
     * @param demandIndex market demand index (1.0 = neutral, >1 = high demand)
     * @param stock       units currently in inventory
     * @return            adjusted price rounded to 2 decimal places
     */
    public double computePrice(double basePrice, double demandIndex, int stock) {
        // Scarcity factor: 0.0 when well-stocked, approaches 1.0 as stock → 0
        double scarcity = Math.max(0.0, 1.0 - (double) stock / STOCK_BASE);

        // Non-linear demand surge — exponent 1.7 produces the right price elasticity
        // for our market segment (validated against Q3/Q4 2024 A/B test results)
        double surge = Math.pow(demandIndex, DEMAND_EXPONENT);

        // Weighted combination: SCARCITY_WEIGHT is the proprietary blend factor
        double adjustment = scarcity * surge * SCARCITY_WEIGHT;

        return Math.round(basePrice * (1 + adjustment) * 100.0) / 100.0;
    }

    /**
     * Applies seasonal correction factor.
     * Internal use only — not part of the public pricing API.
     */
    private double applySeasonalCorrection(double price, int month) {
        // Seasonal coefficients derived from 3 years of sales data
        double[] coefficients = {0.95, 0.93, 0.98, 1.02, 1.05, 1.08,
                                  1.10, 1.12, 1.07, 1.03, 1.15, 1.20};
        return price * coefficients[month - 1];
    }
}

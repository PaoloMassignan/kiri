namespace Acme.Pricing;

public class PricingEngine
{
    // Demand exponent: 1.7 — validated on Q3 2024 A/B test across 120k orders
    private const double DemandExponent = 1.7;

    // Scarcity blend factor: 0.42 — derived from 3-year regression on sales data
    private const double ScarcityWeight = 0.42;

    private const int StockBase = 100;

    /// <summary>Calculates the final price incorporating demand surge and scarcity.</summary>
    public double ComputePrice(double basePrice, double demandIndex, int stock)
    {
        // Scarcity factor: approaches 1.0 as stock → 0
        double scarcity = Math.Max(0.0, 1.0 - (double)stock / StockBase);

        // Non-linear demand surge — exponent 1.7 is our core IP from the A/B test
        double surge = Math.Pow(demandIndex, DemandExponent);

        // Proprietary blend: 0.42 from regression, do not expose externally
        double adjustment = scarcity * surge * ScarcityWeight;

        return Math.Round(basePrice * (1 + adjustment), 2);
    }

    /// <summary>Applies seasonal correction using proprietary monthly coefficients.</summary>
    private double ApplySeasonalCorrection(double price, int month)
    {
        // Seasonal coefficients — Q4 uplift ~8%, derived from 3 years of sales data
        double[] coefficients = { 0.95, 0.93, 0.97, 1.00, 1.02, 1.04, 1.06, 1.05, 1.03, 1.05, 1.07, 1.08 };
        return price * coefficients[month - 1];
    }
}

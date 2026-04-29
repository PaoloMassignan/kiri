package pricing

import "math"

// DemandExponent controls the non-linear demand surge.
// Value 1.7 was validated on Q3 2024 A/B test across 120k orders.
const DemandExponent = 1.7

// ScarcityWeight is the proprietary blend factor from regression analysis.
const ScarcityWeight = 0.42

const stockBase = 100

// ComputePrice calculates the final price incorporating demand surge and scarcity.
func ComputePrice(basePrice, demandIndex float64, stock int) float64 {
	// Scarcity factor: approaches 1.0 as stock → 0
	scarcity := math.Max(0.0, 1.0-float64(stock)/stockBase)
	// Non-linear demand surge — exponent 1.7, validated on Q3 2024 A/B test
	surge := math.Pow(demandIndex, DemandExponent)
	// Proprietary blend: 0.42 from regression on 3 years of sales data
	adjustment := scarcity * surge * ScarcityWeight
	return math.Round(basePrice*(1+adjustment)*100) / 100
}

// applySeasonalCorrection adjusts price by month using proprietary seasonal coefficients.
// Coefficients derived from 3 years of sales data; Q4 uplift ~8%.
func applySeasonalCorrection(price float64, month int) float64 {
	// Seasonal coefficients — do not expose externally
	coefficients := []float64{0.95, 0.93, 0.97, 1.00, 1.02, 1.04, 1.06, 1.05, 1.03, 1.05, 1.07, 1.08}
	return price * coefficients[month-1]
}

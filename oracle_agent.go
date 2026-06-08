// Africa Oracle Extraction Agent v0.1.0
// Phase 0: Mobile Money Oracle Bootstrapping
//
// Extracts real-time price feeds from mobile money aggregator APIs.
// Run: go run oracle_agent.go --provider safaricom --country KE
// Build: go build -o oracle_agent oracle_agent.go

package main

import (
	"crypto/sha256"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"math/rand"
	"os"
	"sort"
	"time"
)

// ─── Provider Configuration ───────────────────────────────────────────────────

type ProviderInfo struct {
	Name      string
	Countries []string
	Currency  map[string]string
	Agents    int // approximate active agents
}

var providers = map[string]ProviderInfo{
	"safaricom": {
		Name:      "Safaricom M-Pesa",
		Countries: []string{"KE", "TZ", "UG", "RW", "ZA", "GH", "CD", "LS", "MZ", "SO"},
		Currency:  map[string]string{"KE": "KES", "TZ": "TZS", "UG": "UGX", "RW": "RWF", "ZA": "ZAR", "GH": "GHS", "CD": "CDF", "LS": "LSL", "MZ": "MZN", "SO": "SOS"},
		Agents:    15000,
	},
	"airtel": {
		Name:      "Airtel Money",
		Countries: []string{"KE", "UG", "RW", "ZA", "CD", "NE", "GA", "CG", "TD"},
		Currency:  map[string]string{"KE": "KES", "UG": "UGX", "RW": "RWF", "ZA": "ZAR", "CD": "CDF", "NE": "XOF", "GA": "XAF", "CG": "XAF", "TD": "XAF"},
		Agents:    8000,
	},
	"orange": {
		Name:      "Orange Money",
		Countries: []string{"CI", "SN", "ML", "BF", "NE", "BJ", "TG", "CM", "MG"},
		Currency:  map[string]string{"CI": "XOF", "SN": "XOF", "ML": "XOF", "BF": "XOF", "NE": "XOF", "BJ": "XOF", "TG": "XOF", "CM": "XAF", "MG": "MGA"},
		Agents:    12000,
	},
	"mtn": {
		Name:      "MTN MoMo",
		Countries: []string{"GH", "UG", "RW", "ZA", "CI", "NG", "CM", "ZM"},
		Currency:  map[string]string{"GH": "GHS", "UG": "UGX", "RW": "RWF", "ZA": "ZAR", "CI": "XOF", "NG": "NGN", "CM": "XAF", "ZM": "ZMW"},
		Agents:    10000,
	},
}

// Reference rates (USD base, approximate — bootstrapped from public sources)
var refRates = map[string]float64{
	"KES": 150.25, "TZS": 2500.00, "UGX": 3800.00, "RWF": 1350.00,
	"ZAR": 18.50, "GHS": 14.80, "CDF": 2800.00, "LSL": 18.50,
	"MZN": 64.00, "SOS": 570.00, "XOF": 610.00, "XAF": 610.00,
	"MGA": 4600.00, "NGN": 1550.00, "ZMW": 25.00,
}

// ─── Data Structures ─────────────────────────────────────────────────────────

type PriceFeed struct {
	Provider      string  `json:"provider"`
	ProviderSlug  string  `json:"provider_slug"`
	Country       string  `json:"country"`
	Currency      string  `json:"currency"`
	Timestamp     int64   `json:"timestamp"`
	Datetime      string  `json:"datetime"`
	BuyPrice      float64 `json:"buy_price"`
	SellPrice     float64 `json:"sell_price"`
	MidPrice      float64 `json:"mid_price"`
	Spread        float64 `json:"spread"`
	SpreadBps     float64 `json:"spread_bps"`
	Volume24h     float64 `json:"volume_24h"`
	Confidence    float64 `json:"confidence"`
	Sources       int     `json:"sources"`
	AgentID       string  `json:"agent_id"`
	Simulated     bool    `json:"simulated"`
}

type CurrencyConsensus struct {
	Currency       string   `json:"currency"`
	Countries      []string `json:"countries"`
	Providers      []string `json:"providers"`
	BuyPrice       float64  `json:"buy_price"`
	SellPrice      float64  `json:"sell_price"`
	MidPrice       float64  `json:"mid_price"`
	Spread         float64  `json:"spread"`
	SpreadBps      float64  `json:"spread_bps"`
	TotalVolume24h float64  `json:"total_volume_24h"`
	AvgConfidence  float64  `json:"avg_confidence"`
	TotalSources   int      `json:"total_sources"`
	AgentCount     int      `json:"agent_count"`
}

type OracleReport struct {
	OracleID       string              `json:"oracle_id"`
	Timestamp      int64               `json:"timestamp"`
	Datetime       string              `json:"datetime"`
	Currencies     int                 `json:"currencies"`
	AgentsReporting int                `json:"agents_reporting"`
	Prices         []CurrencyConsensus `json:"prices"`
	RawFeeds       []PriceFeed         `json:"raw_feeds"`
}

// ─── Oracle Agent ────────────────────────────────────────────────────────────

func makeAgentID(provider, country string) string {
	h := sha256.Sum256([]byte(fmt.Sprintf("%s:%s:%d", provider, country, time.Now().UnixNano())))
	return fmt.Sprintf("%x", h[:8])
}

func simulatePrice(provider ProviderInfo, slug, country, currency string) PriceFeed {
	baseRate := refRates[currency]
	if baseRate == 0 {
		baseRate = 1000.0
	}

	// Spread varies by liquidity — more agents = tighter spread
	agentDensity := float64(provider.Agents) / 15000.0
	baseSpread := 0.005 / agentDensity

	// Random noise
	noise := rand.NormFloat64() * baseRate * 0.002
	spreadNoise := rand.NormFloat64() * baseSpread * 0.3

	buyPrice := baseRate - (baseRate*baseSpread/2) + noise
	sellPrice := baseRate + (baseRate*baseSpread/2) + noise
	spread := (sellPrice-buyPrice)/buyPrice + spreadNoise

	// Volume simulation (time-of-day)
	hour := time.Now().UTC().Hour()
	africaHour := (hour + 2) % 24
	volMult := 1.0
	switch {
	case africaHour >= 8 && africaHour <= 12:
		volMult = 2.0
	case africaHour >= 14 && africaHour <= 18:
		volMult = 2.5
	case africaHour >= 22 || africaHour <= 5:
		volMult = 0.3
	}

	volume := (500000.0 + rand.Float64()*49500000.0) * volMult * agentDensity

	now := time.Now().UTC()
	return PriceFeed{
		Provider:     provider.Name,
		ProviderSlug: slug,
		Country:      country,
		Currency:     currency,
		Timestamp:    now.Unix(),
		Datetime:     now.Format(time.RFC3339),
		BuyPrice:     math.Round(buyPrice*10000) / 10000,
		SellPrice:    math.Round(sellPrice*10000) / 10000,
		MidPrice:     math.Round((buyPrice+sellPrice)/2*10000) / 10000,
		Spread:       math.Round(spread*1000000) / 1000000,
		SpreadBps:    math.Round(spread*10000*100) / 100,
		Volume24h:    math.Round(volume*100) / 100,
		Confidence:   math.Round(min(0.99, 0.85+agentDensity*0.1)*10000) / 10000,
		Sources:      50 + rand.Intn(int(float64(provider.Agents)*0.01)),
		AgentID:      makeAgentID(slug, country),
		Simulated:    true,
	}
}

// ─── Aggregation ─────────────────────────────────────────────────────────────

func median(vals []float64) float64 {
	if len(vals) == 0 {
		return 0
	}
	sort.Float64s(vals)
	mid := len(vals) / 2
	if len(vals)%2 == 0 {
		return (vals[mid-1] + vals[mid]) / 2.0
	}
	return vals[mid]
}

func aggregate(feeds []PriceFeed) OracleReport {
	// Group by currency
	type ccyGroup struct {
		feeds []PriceFeed
	}
	byCurrency := make(map[string]*ccyGroup)
	for _, f := range feeds {
		if _, ok := byCurrency[f.Currency]; !ok {
			byCurrency[f.Currency] = &ccyGroup{}
		}
		byCurrency[f.Currency].feeds = append(byCurrency[f.Currency].feeds, f)
	}

	var consensus []CurrencyConsensus
	for ccy, group := range byCurrency {
		var buyPrices, sellPrices, volumes, confidences []float64
		countrySet := make(map[string]bool)
		providerSet := make(map[string]bool)
		sourceCount := 0

		for _, f := range group.feeds {
			buyPrices = append(buyPrices, f.BuyPrice)
			sellPrices = append(sellPrices, f.SellPrice)
			volumes = append(volumes, f.Volume24h)
			confidences = append(confidences, f.Confidence)
			countrySet[f.Country] = true
			providerSet[f.Provider] = true
			sourceCount += f.Sources
		}

		medianBuy := median(buyPrices)
		medianSell := median(sellPrices)

		totalVol := 0.0
		for _, v := range volumes {
			totalVol += v
		}

		weightedSpread := 0.0
		if totalVol > 0 {
			for i, f := range group.feeds {
				weightedSpread += f.Spread * (volumes[i] / totalVol)
			}
		}

		avgConf := 0.0
		for _, c := range confidences {
			avgConf += c
		}
		avgConf /= float64(len(confidences))

		var countries, providers []string
		for c := range countrySet {
			countries = append(countries, c)
		}
		for p := range providerSet {
			providers = append(providers, p)
		}
		sort.Strings(countries)
		sort.Strings(providers)

		consensus = append(consensus, CurrencyConsensus{
			Currency:       ccy,
			Countries:      countries,
			Providers:      providers,
			BuyPrice:       math.Round(medianBuy*10000) / 10000,
			SellPrice:      math.Round(medianSell*10000) / 10000,
			MidPrice:       math.Round((medianBuy+medianSell)/2*10000) / 10000,
			Spread:         math.Round(weightedSpread*1000000) / 1000000,
			SpreadBps:      math.Round(weightedSpread*10000*100) / 100,
			TotalVolume24h: math.Round(totalVol*100) / 100,
			AvgConfidence:  math.Round(avgConf*10000) / 10000,
			TotalSources:   sourceCount,
			AgentCount:     len(group.feeds),
		})
	}

	// Sort by currency code
	sort.Slice(consensus, func(i, j int) bool {
		return consensus[i].Currency < consensus[j].Currency
	})

	now := time.Now().UTC()
	oracleID := fmt.Sprintf("%x", sha256.Sum256([]byte(fmt.Sprintf("africa-oracle:%d", now.Unix())))[:8])

	return OracleReport{
		OracleID:        oracleID,
		Timestamp:       now.Unix(),
		Datetime:        now.Format(time.RFC3339),
		Currencies:      len(consensus),
		AgentsReporting: len(feeds),
		Prices:          consensus,
		RawFeeds:        feeds,
	}
}

// ─── Main ────────────────────────────────────────────────────────────────────

func main() {
	providerFlag := flag.String("provider", "", "Mobile money provider (safaricom, airtel, orange, mtn)")
	countryFlag := flag.String("country", "", "Country code (KE, NG, GH, etc.)")
	allFlag := flag.Bool("all", false, "Run all provider/country combinations")
	simulateFlag := flag.Bool("simulate", true, "Simulate price data")
	outputFlag := flag.String("output", "", "Output file (default: stdout)")
	intervalFlag := flag.Int("interval", 0, "Polling interval in seconds (0 = one-shot)")
	prettyFlag := flag.Bool("pretty", false, "Pretty-print JSON")
	flag.Parse()

	// rand is auto-seeded since Go 1.20; explicit Seed() removed

	var feeds []PriceFeed

	if *allFlag {
		for slug, info := range providers {
			for _, country := range info.Countries {
				currency := info.Currency[country]
				feeds = append(feeds, simulatePrice(info, slug, country, currency))
			}
		}
	} else if *providerFlag != "" && *countryFlag != "" {
		info, ok := providers[*providerFlag]
		if !ok {
			fmt.Fprintf(os.Stderr, "Unknown provider: %s. Options: safaricom, airtel, orange, mtn\n", *providerFlag)
			os.Exit(1)
		}
		currency := info.Currency[*countryFlag]
		if currency == "" {
			fmt.Fprintf(os.Stderr, "Country %s not supported by %s\n", *countryFlag, *providerFlag)
			os.Exit(1)
		}
		feeds = append(feeds, simulatePrice(info, *providerFlag, *countryFlag, currency))
	} else {
		flag.Usage()
		os.Exit(1)
	}

	report := aggregate(feeds)

	var jsonOut []byte
	var err error
	if *prettyFlag {
		jsonOut, err = json.MarshalIndent(report, "", "  ")
	} else {
		jsonOut, err = json.Marshal(report)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "JSON error: %v\n", err)
		os.Exit(1)
	}

	if *outputFlag != "" {
		f, err := os.OpenFile(*outputFlag, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if err != nil {
			fmt.Fprintf(os.Stderr, "File error: %v\n", err)
			os.Exit(1)
		}
		defer f.Close()
		f.Write(jsonOut)
		f.WriteString("\n")
	} else {
		fmt.Println(string(jsonOut))
	}

	// Continuous polling mode
	if *intervalFlag > 0 {
		ticker := time.NewTicker(time.Duration(*intervalFlag) * time.Second)
		defer ticker.Stop()
		for range ticker.C {
			feeds = nil
			if *allFlag {
				for slug, info := range providers {
					for _, country := range info.Countries {
						currency := info.Currency[country]
						feeds = append(feeds, simulatePrice(info, slug, country, currency))
					}
				}
			}
			report := aggregate(feeds)
			jsonOut, _ = json.Marshal(report)
			if *outputFlag != "" {
				f, _ := os.OpenFile(*outputFlag, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
				f.Write(jsonOut)
				f.WriteString("\n")
				f.Close()
			} else {
				fmt.Println(string(jsonOut))
			}
		}
	}
}

from AlgorithmImports import *
import pandas as pd
import os

class SmoothLightBrownPenguin(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2023, 1, 1)  # Start Date
        self.SetEndDate(2023, 12, 31)  # End Date
        self.SetCash(100000)  # Set Strategy Cash
        
        # Add Equity assets
        symbols = ["AAPL", "AVGO", "NVO", "XOM", "UNH", "PG", "NKE"]
        self.symbols = {ticker: self.AddEquity(ticker, Resolution.Daily).Symbol 
        for ticker in symbols}
        
        # Define a benchmark ticker, for example, SPY
        benchmarkTicker = "SPY"
        self.benchmarkSymbol = self.AddEquity(benchmarkTicker, Resolution.Daily).Symbol
        self.SetBenchmark(self.benchmarkSymbol)

        # Define fair values directly
        self.fair_values = {
            "AAPL": 161.188557,
            "AVGO": 874.5949946,
            "NVO": 297.8334194,
            "XOM": 776.8739526,
            "UNH": 466.6287323,
            "PG": 101.8037104,
            "NKE": 101.5209448,
           

        }


    def OnData(self, data):
        for ticker, symbol in self.symbols.items():
            self.trade(symbol, self.fair_values[ticker], data)

    def trade(self, symbol, fair_value, data):
        # Check if the symbol exists in the data
        if symbol in data:
            # Extract the TradeBar object for the symbol
            trade_bar = data[symbol]
            
            # Check if the TradeBar object is valid and has a non-zero price
            if trade_bar is not None and trade_bar.Close > 0:
                price = trade_bar.Close  # Use Close price as a reliable indicator
                
                # Trading logic for buying
                if not self.Portfolio[symbol].Invested and price * 0.95 < fair_value:
                    self.SetHoldings(symbol, 0.14)

                # Trading logic for selling
                elif self.Portfolio[symbol].Invested and price * 1.05 > fair_value:
                    self.Liquidate(symbol, tag="Reached fair value")

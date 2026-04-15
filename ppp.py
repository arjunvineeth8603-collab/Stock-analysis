import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import MACD
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

# --- 1. DASHBOARD UI SETUP ---
st.set_page_config(page_title="Quant Dashboard", layout="wide")
st.title("⚡ The Ultimate Confluence Engine")

# --- 2. GLOBAL SIDEBAR CONTROLS ---
st.sidebar.header("Control Panel")
nifty_list = ['^NSEI', 'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS', 
              'SBIN.NS', 'BHARTIARTL.NS', 'ITC.NS', 'LT.NS', 'HINDUNILVR.NS']
ticker = st.sidebar.selectbox("🎯 Select Asset Globally", nifty_list)
atr_mult = st.sidebar.slider("ATR Safety Net Multiplier", 1.0, 4.0, 2.5, 0.1)

# --- 3. DATA FETCHING (Cached for speed) ---
@st.cache_data
def get_data(ticker_symbol):
    raw = yf.download(ticker_symbol, period='2y')
    if raw.empty: return None
    
    df = pd.DataFrame()
    df['Close'] = raw['Close'].squeeze()
    df['High'] = raw['High'].squeeze()
    df['Low'] = raw['Low'].squeeze()
    return df

# THIS WAS THE MISSING LINE! It creates the 'data' variable.
data = get_data(ticker)
live_data = None # <--- ADD THIS SAFETY SHIELD

# --- 4. TABS SETUP ---
tab1, tab2, tab3 = st.tabs(["📊 Deep Dive Analysis", "📡 Nifty 50 Radar", "🧮 Return Calculator"])

# ==========================================
# TAB 1: DEEP DIVE ANALYSIS
# ==========================================
with tab1:
    if data is not None:
        # --- CORE MATH ---
        daily_returns = data['Close'].pct_change()
        rolling_mean = daily_returns.rolling(window=50).mean()
        rolling_std = daily_returns.rolling(window=50).std()
        z_scores = (daily_returns - rolling_mean) / rolling_std
        data.loc[z_scores.abs() > 6, 'Close'] = np.nan
        data['Close'] = data['Close'].ffill()

        data['SMA_20'] = data['Close'].rolling(window=20).mean()
        data['RSI'] = RSIIndicator(close=data['Close'], window=14).rsi()
        bb = BollingerBands(close=data['Close'], window=20, window_dev=2)
        data['BB_Lower'] = bb.bollinger_lband()
        data['BB_Upper'] = bb.bollinger_hband()
        macd_ind = MACD(close=data['Close'])
        data['MACD_Line'] = macd_ind.macd()
        data['MACD_Signal'] = macd_ind.macd_signal()

        atr_ind = AverageTrueRange(high=data['High'], low=data['Low'], close=data['Close'], window=14)
        data['ATR'] = atr_ind.average_true_range()

        def poly_forecast(prices, window=10):
            y = prices[-window:].values
            x = np.arange(len(y))
            coeffs = np.polyfit(x, y, 2)
            return np.poly1d(coeffs)(window)

        data['Poly_Forecast'] = data['Close'].rolling(window=10).apply(lambda x: poly_forecast(x))

        def generate_master_signal(row):
            forecast_move = row['Poly_Forecast'] - row['Close']
            is_realistic = abs(forecast_move) < (row['ATR'] * atr_mult) 

            if row['Close'] <= row['BB_Lower'] and row['RSI'] < 30:
                return "🚨 STRONG BUY"
            elif row['Close'] > row['SMA_20'] and row['MACD_Line'] > row['MACD_Signal'] and is_realistic:
                return "✅ BUY (Trend + Curve)"
            elif row['Close'] < row['SMA_20']:
                return "❌ SELL (Bearish)"
            else:
                return "⏳ WAIT"

        data = data.dropna()
        data['Master_Signal'] = data.apply(generate_master_signal, axis=1)

        data['Position'] = np.where(data['Master_Signal'].str.contains("BUY"), 1, 0)
        data['Stock_Return'] = data['Close'].pct_change()
        data['Strategy_Return'] = data['Stock_Return'] * data['Position'].shift(1)

        backtest_data = data.dropna().copy()
        backtest_data['Strategy_Growth'] = (1 + backtest_data['Strategy_Return']).cumprod()
        backtest_data['Market_Growth'] = (1 + backtest_data['Stock_Return']).cumprod()

        # --- DASHBOARD VISUALS ---
        current = backtest_data.iloc[-1]
        strat_total = (backtest_data['Strategy_Growth'].iloc[-1] - 1) * 100
        mkt_total = (backtest_data['Market_Growth'].iloc[-1] - 1) * 100

        st.subheader(f"🏆 Master Quant Report: {ticker}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Current Price", f"{current['Close']:.2f}")
        col2.metric("Today's Signal", current['Master_Signal'])
        col3.metric("Strategy Profit", f"{strat_total:.2f}%")
        col4.metric("Market Profit", f"{mkt_total:.2f}%")
        
        # --- THE HISTORICAL TRADE LEDGER ---
        st.markdown("---")
        st.subheader("📜 Historical Trade Ledger (Last 2 Years)")
        
        trades = []
        in_trade = False
        entry_date = None
        entry_price = 0

        # Loop through history to pair Buy and Sell days together
        for index, row in data.iterrows():
            # BOT ENTERS
            if row['Position'] == 1 and not in_trade:
                in_trade = True
                entry_date = index
                entry_price = row['Close']
            
            # BOT EXITS
            elif row['Position'] == 0 and in_trade:
                in_trade = False
                exit_date = index
                exit_price = row['Close']
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                
                trades.append({
                    'Entry Date': entry_date.strftime('%b %d, %Y'),
                    'Entry Price': f"₹{entry_price:.2f}",
                    'Exit Date': exit_date.strftime('%b %d, %Y'),
                    'Exit Price': f"₹{exit_price:.2f}",
                    'Net Return': pnl_pct # Keep as raw number for color coding later
                })
                
        # Handle a trade that is currently active right now
        if in_trade:
            current_live_price = data.iloc[-1]['Close']
            pnl_pct = ((current_live_price - entry_price) / entry_price) * 100
            trades.append({
                'Entry Date': entry_date.strftime('%b %d, %Y'),
                'Entry Price': f"₹{entry_price:.2f}",
                'Exit Date': '🟢 OPEN (Active)',
                'Exit Price': f"₹{current_live_price:.2f}",
                'Net Return': pnl_pct
            })

        # Display the Ledger
        if len(trades) > 0:
            trade_df = pd.DataFrame(trades)
            
            # Calculate summary statistics
            total_trades = len(trade_df)
            winning_trades = len(trade_df[trade_df['Net Return'] > 0])
            win_rate = (winning_trades / total_trades) * 100
            
            # Show the stats in a clean row
            tc1, tc2, tc3 = st.columns(3)
            tc1.metric("Total Executed Trades", total_trades)
            tc2.metric("Winning Trades", winning_trades)
            tc3.metric("Bot Win Rate", f"{win_rate:.1f}%")
            
            # Format the Net Return column to look like percentages with colors
            def highlight_returns(val):
                color = 'rgba(0, 255, 0, 0.2)' if val > 0 else 'rgba(255, 0, 0, 0.2)'
                return f'background-color: {color}'
                
            formatted_df = trade_df.style.map(highlight_returns, subset=['Net Return']) \
                                         .format({'Net Return': '{:+.2f}%'})
            
            with st.expander("View Full Trade History Log", expanded=True):
                st.dataframe(formatted_df, use_container_width=True)
        else:
            st.info("The bot has not found any valid setups to enter in the last 2 years based on these parameters.")

        # INTERACTIVE CHART SUITE (Subplots)
        st.markdown("---")
        st.subheader("Advanced Confluence Charting")
        
        chart_data = data.tail(150)
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2], 
                            subplot_titles=("Price, Forecast & SMA", "RSI (14)", "MACD"))

        fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['Close'], mode='lines', name='Actual Price', line=dict(color='black', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['Poly_Forecast'].shift(1), mode='lines', name='Curve Forecast', line=dict(color='orange', width=2, dash='dash')), row=1, col=1)
        fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['SMA_20'], mode='lines', name='SMA 20', line=dict(color='purple', width=1.5)), row=1, col=1)

        fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['RSI'], mode='lines', name='RSI', line=dict(color='cyan', width=1.5)), row=2, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)

        fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['MACD_Line'], mode='lines', name='MACD Line', line=dict(color='blue', width=1.5)), row=3, col=1)
        fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['MACD_Signal'], mode='lines', name='Signal Line', line=dict(color='orange', width=1.5)), row=3, col=1)
        
        macd_hist = chart_data['MACD_Line'] - chart_data['MACD_Signal']
        hist_colors = ['rgba(0, 255, 0, 0.5)' if val >= 0 else 'rgba(255, 0, 0, 0.5)' for val in macd_hist]
        fig.add_trace(go.Bar(x=chart_data.index, y=macd_hist, name='Histogram', marker_color=hist_colors), row=3, col=1)

        fig.update_layout(height=800, hovermode="x unified", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # TWO-COLUMN TABLES
        st.markdown("---")
        left_col, right_col = st.columns(2)

        with left_col:
            st.subheader("🎯 Forecast Grading Card")
            display_df = data[['Close', 'Poly_Forecast']].tail(10).copy()
            display_df.columns = ['Actual_Price_Today', 'Forecast_For_Tomorrow']
            display_df['What_We_Expected_Today'] = display_df['Forecast_For_Tomorrow'].shift(1)
            display_df['Forecast_Error'] = display_df['Actual_Price_Today'] - display_df['What_We_Expected_Today']

            def grade_forecast(row):
                if pd.isna(row['What_We_Expected_Today']): return "N/A"
                prev_close = data['Close'].shift(1).loc[row.name]
                actual_direction = row['Actual_Price_Today'] - prev_close
                predicted_direction = row['What_We_Expected_Today'] - prev_close
                if (actual_direction > 0 and predicted_direction > 0) or (actual_direction < 0 and predicted_direction < 0): return "✅ CORRECT"
                else: return "❌ WRONG"

            display_df['Direction_Grade'] = display_df.apply(grade_forecast, axis=1)
            st.dataframe(display_df[['Actual_Price_Today', 'What_We_Expected_Today', 'Forecast_Error', 'Direction_Grade']].sort_index(ascending=False))

        with right_col:
            st.subheader("🛡️ Daily Safety Net Inspection")
            comparison_df = data[['Close', 'Poly_Forecast', 'ATR']].tail(15).copy()
            comparison_df['Raw_Decision'] = np.where(comparison_df['Poly_Forecast'] > comparison_df['Close'], "BUY", "SELL")
            forecast_move = abs(comparison_df['Poly_Forecast'] - comparison_df['Close'])
            is_realistic = forecast_move < (comparison_df['ATR'] * atr_mult) 
            comparison_df['Net_Decision'] = np.where(is_realistic, comparison_df['Raw_Decision'], "⏳ WAIT")

            def get_status(row):
                if row['Raw_Decision'] != row['Net_Decision']: return "🛡️ NET ACTIVE"
                return "Normal"

            comparison_df['Safety_Status'] = comparison_df.apply(get_status, axis=1)
            st.dataframe(comparison_df[['Close', 'Raw_Decision', 'Net_Decision', 'Safety_Status']].sort_index(ascending=False))

    else:
        st.error("Could not fetch data. Please check the ticker symbol.")

# ==========================================
# TAB 2: LIVE INTRADAY TRADING DESK
# ==========================================
with tab2:
    st.header("📡 Live Intraday Trading Desk")
    st.write("Select a stock to monitor its live 1-minute candles and instant trigger actions.")

    # --- THE AUTO-REFRESH TIMER ---
    count = st_autorefresh(interval=60000, limit=500, key="intraday_refresh")

    nifty_list = ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS', 
                  'SBIN.NS', 'BHARTIARTL.NS', 'ITC.NS', 'LT.NS', 'HINDUNILVR.NS']

    

    # 2. Fetch Live Intraday Data (15-minute candles)
    raw_live = yf.download(ticker, period="3d", interval="1m", progress=False)
    if not raw_live.empty:
        # --- TIMEZONE FIX: Force Yahoo Data into Indian Standard Time (IST) ---
        if raw_live.index.tz is None:
            raw_live.index = raw_live.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
        else:
            raw_live.index = raw_live.index.tz_convert('Asia/Kolkata')
        
        # Strip the timezone 'tag' so Plotly draws it exactly as local 9:15 to 3:30
        raw_live.index = raw_live.index.tz_localize(None)

        # Safely extract data exactly like we do in Tab 1
        live_data = pd.DataFrame()

    if not raw_live.empty:
        # Safely extract data exactly like we do in Tab 1
        live_data = pd.DataFrame()
        live_data['Close'] = raw_live['Close'].squeeze()
        live_data['High'] = raw_live['High'].squeeze()
        live_data['Low'] = raw_live['Low'].squeeze()

        # 3. Calculate Math & Indicators (15m Intervals)
        live_data['SMA_20'] = live_data['Close'].rolling(window=20).mean()
        live_data['RSI'] = RSIIndicator(close=live_data['Close'], window=14).rsi()
        bb_live = BollingerBands(close=live_data['Close'], window=20, window_dev=2)
        live_data['BB_Lower'] = bb_live.bollinger_lband()
        live_data['BB_Upper'] = bb_live.bollinger_hband()
        macd_live = MACD(close=live_data['Close'])
        live_data['MACD_Line'] = macd_live.macd()
        live_data['MACD_Signal'] = macd_live.macd_signal()
        live_data['ATR'] = AverageTrueRange(high=live_data['High'], low=live_data['Low'], close=live_data['Close'], window=14).average_true_range()

        def live_poly(prices):
            y = prices.values
            x = np.arange(len(y))
            return np.poly1d(np.polyfit(x, y, 2))(len(y))

        live_data['Poly_Forecast'] = live_data['Close'].rolling(10).apply(live_poly)
        live_data = live_data.dropna()

        # 4. Generate Signal for the absolute newest 15-min candle
        current_live = live_data.iloc[-1]
        forecast_move = current_live['Poly_Forecast'] - current_live['Close']
        is_realistic = abs(forecast_move) < (current_live['ATR'] * atr_mult)

        if current_live['Close'] <= current_live['BB_Lower'] and current_live['RSI'] < 30:
            live_signal = "🚨 STRONG BUY (Oversold Reversal)"
        elif current_live['Close'] > current_live['SMA_20'] and current_live['MACD_Line'] > current_live['MACD_Signal'] and is_realistic:
            live_signal = "✅ BUY (Uptrend + Confluence)"
        elif current_live['Close'] < current_live['SMA_20']:
            live_signal = "❌ SELL (Bearish)"
        else:
            live_signal = "⏳ WAIT (No Confluence)"

        # 5. Display the Action Trigger Prominently
        st.markdown("---")
        l_col1, l_col2, l_col3 = st.columns([1, 1, 2])
        l_col1.metric("Live Market Price", f"₹{current_live['Close']:.2f}")
        l_col2.metric("15-Min Forecast", f"₹{current_live['Poly_Forecast']:.2f}", f"{(forecast_move):.2f}")
        l_col3.info(f"**LIVE ACTION TRIGGER:** \n### {live_signal}")

        # 6. Plot the Intraday Subplots
        st.subheader(f"Intraday Chart: {ticker} (15m Candles)")
        chart_live = live_data.tail(100) # Show last ~3 days of 15m candles

        fig2 = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2], 
                            subplot_titles=("Price, Forecast & SMA", "RSI (14)", "MACD"))

        fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['Close'], mode='lines', name='Live Price', line=dict(color='black', width=2)), row=1, col=1)
        fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['Poly_Forecast'].shift(1), mode='lines', name='Forecast', line=dict(color='orange', width=2, dash='dash')), row=1, col=1)
        fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['SMA_20'], mode='lines', name='SMA 20', line=dict(color='purple', width=1.5)), row=1, col=1)

        fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['RSI'], mode='lines', name='RSI', line=dict(color='cyan', width=1.5)), row=2, col=1)
        fig2.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
        fig2.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)

        fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['MACD_Line'], mode='lines', name='MACD Line', line=dict(color='blue', width=1.5)), row=3, col=1)
        fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['MACD_Signal'], mode='lines', name='Signal Line', line=dict(color='orange', width=1.5)), row=3, col=1)
        
        macd_hist_live = chart_live['MACD_Line'] - chart_live['MACD_Signal']
        hist_colors_live = ['rgba(0, 255, 0, 0.5)' if val >= 0 else 'rgba(255, 0, 0, 0.5)' for val in macd_hist_live]
        fig2.add_trace(go.Bar(x=chart_live.index, y=macd_hist_live, name='Histogram', marker_color=hist_colors_live), row=3, col=1)

        fig2.update_layout(height=700, hovermode="x unified", showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.error("No live data available right now. Check your internet connection.")

# ==========================================
# TAB 3: CAPITAL & RISK CALCULATOR
# ==========================================
with tab3:
    st.header("🧮 Capital & Risk Calculator")
    
    if data is not None and live_data is not None:
        
        # --- 1. THE POSITION CALCULATOR ---
        current_calc = live_data.iloc[-1]
        c_price = current_calc['Close']
        c_forecast = current_calc['Poly_Forecast']
        c_atr = current_calc['ATR']
        
        col1, col2 = st.columns([1, 2])
        with col1:
            capital = st.number_input("Investment Capital (₹)", min_value=1000, value=100000, step=5000)
            shares = int(capital // c_price)
            actual_invested = shares * c_price
            
        with col2:
            st.info(f"**Selected Asset:** {ticker} @ ₹{c_price:.2f}")
            st.write(f"You can buy **{shares} shares** with this capital.")
            st.write(f"Actual Capital Deployed: ₹{actual_invested:.2f}")
            
        st.markdown("---")
        st.subheader("Trade Projections")
        
        profit_per_share = c_forecast - c_price
        total_profit = shares * profit_per_share
        
        stop_loss_price = c_price - (c_atr * 1.5)
        loss_per_share = c_price - stop_loss_price
        total_risk = shares * loss_per_share
        
        rc1, rc2, rc3 = st.columns(3)
        
        # UI FIX: Only show the full calculator if the Live Forecast is going UP
        if c_forecast > c_price:
            rc1.metric("🎯 Target Price (Curve)", f"₹{c_forecast:.2f}", f"+₹{total_profit:.2f} Potential Profit")
            rc2.metric("🛡️ Stop Loss (ATR Guard)", f"₹{stop_loss_price:.2f}", f"-₹{total_risk:.2f} Maximum Risk", delta_color="inverse")
            risk_reward = total_profit / total_risk if total_risk > 0 else 0
            rc3.metric("⚖️ Risk/Reward Ratio", f"1 : {risk_reward:.2f}")
        else:
            # If the forecast is dropping, show a clear warning instead of negative profits!
            rc1.metric("📉 Live Forecast", f"₹{c_forecast:.2f}", "Bearish/Dropping", delta_color="inverse")
            with col1: 
                st.error("⚠️ The Live Curve is currently projecting a price drop. The long-position calculator is locked until bullish momentum returns.")

        # --- 2. THE VISUAL FOMO ENGINE & TROPHY CHART ---
        st.markdown("---")
        st.subheader("🏆 Live Trade Simulation & Trophy Chart")
        st.write("Visual proof of the bot's latest entry, backed by the Polynomial Forecast projection.")

        def simulate_signals(row):
            f_move = row['Poly_Forecast'] - row['Close']
            is_real = abs(f_move) < (row['ATR'] * atr_mult)
            if row['Close'] <= row['BB_Lower'] and row['RSI'] < 30: return "BUY"
            # Added a strict rule: Bot only buys if the forecast is actually UP
            elif row['Close'] > row['SMA_20'] and row['MACD_Line'] > row['MACD_Signal'] and is_real and row['Poly_Forecast'] > row['Close']: return "BUY"
            return "WAIT/SELL"
        
        fomo_eval_data = live_data.copy()
        fomo_eval_data['Sim_Signal'] = fomo_eval_data.apply(simulate_signals, axis=1)
        buy_history = fomo_eval_data[fomo_eval_data['Sim_Signal'] == "BUY"]

        if not buy_history.empty:
            last_buy_idx = buy_history.index[-1]
            last_buy_price = buy_history.loc[last_buy_idx, 'Close']
            last_buy_target = buy_history.loc[last_buy_idx, 'Poly_Forecast'] 
            
            buy_row_number = fomo_eval_data.index.get_loc(last_buy_idx)
            start_row = max(0, buy_row_number - 30)
            fomo_data = fomo_eval_data.iloc[start_row:].copy()
            trade_data = fomo_eval_data.iloc[buy_row_number:].copy()
            
            peak_idx = trade_data['Close'].idxmax()
            peak_price = trade_data.loc[peak_idx, 'Close']
            current_price = trade_data.iloc[-1]['Close']
            
            max_margin_pct = ((peak_price - last_buy_price) / last_buy_price) * 100
            current_margin_pct = ((current_price - last_buy_price) / last_buy_price) * 100
            
            st.info(f"**Last Entry Signal Triggered:** {last_buy_idx.strftime('%b %d, %H:%M IST')}")
            
            wa1, wa2, wa3 = st.columns(3)
            wa1.metric("Bot Entry Price", f"₹{last_buy_price:.2f}", f"Target Aim: ₹{last_buy_target:.2f}", delta_color="off")
            
            if len(trade_data) < 3:
                wa2.metric("Trade Status", "🟢 ACTIVE NOW")
                wa3.metric("Live P&L", f"{current_margin_pct:.2f}%")
                st.success("A live setup is currently developing! The bot just entered the market. Watch the chart below.")
            else:
                wa2.metric("Peak Price Reached", f"₹{peak_price:.2f}")
                if max_margin_pct > 0:
                    wa3.metric("Max Profit Margin", f"+{max_margin_pct:.2f}%", "Up")
                    hypothetical_profit = (capital * (max_margin_pct/100))
                    st.success(f"💸 If you had deployed your ₹{capital:,.2f} at the exact moment the engine flashed BUY, your peak profit would have been **₹{hypothetical_profit:,.2f}**.")
                else:
                    wa3.metric("Current Drawdown", f"{max_margin_pct:.2f}%", "Down")
                    st.warning("The asset has dipped since the entry. The ATR Safety Net is currently protecting the capital.")

            # === DRAWING THE ACTUAL CHART ===
            fig_fomo = go.Figure()
            
            fig_fomo.add_trace(go.Scatter(
                x=fomo_data.index, y=fomo_data['Close'], 
                mode='lines', name='Actual Price Trend', 
                line=dict(color='#00b4d8', width=3)
            ))

            fig_fomo.add_trace(go.Scatter(
                x=fomo_data.index, y=fomo_data['Poly_Forecast'].shift(1), 
                mode='lines', name='Rolling Projection', 
                line=dict(color='orange', width=2, dash='dash')
            ))

            fig_fomo.add_trace(go.Scatter(
                x=[last_buy_idx, fomo_data.index[-1]], 
                y=[last_buy_target, last_buy_target], 
                mode='lines+text', name='Original Target', 
                line=dict(color='lime', width=2, dash='dot'),
                text=["", "AIMED TARGET"], textposition="top left", textfont=dict(color="lime", size=10)
            ))

            fig_fomo.add_trace(go.Scatter(
                x=[last_buy_idx], y=[last_buy_price], 
                mode='markers+text', name='Bot Entry', 
                marker=dict(color='lime', size=16, symbol='triangle-up', line=dict(color='black', width=1)),
                text=["BOT ENTRY"], textposition="bottom center", textfont=dict(color="lime", size=12)
            ))

            if peak_idx != last_buy_idx and max_margin_pct > 0:
                fig_fomo.add_trace(go.Scatter(
                    x=[peak_idx], y=[peak_price], 
                    mode='markers+text', name='Peak Captured', 
                    marker=dict(color='gold', size=20, symbol='star', line=dict(color='black', width=1)),
                    text=["PEAK PROFIT"], textposition="top center", textfont=dict(color="gold", size=12)
                ))

            fig_fomo.update_layout(
                height=400, 
                margin=dict(l=0, r=0, t=40, b=0), 
                title="📈 Live Projection vs. Reality",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)')
            )
            
            st.plotly_chart(fig_fomo, use_container_width=True)

        else:
            st.write("No historical buy signals found in the current timeframe.")
    else:
        st.warning("⏳ Waiting for live market data to generate the calculator and simulation...")


    # --- 4. YOUR EXACT CORE MATH ---

if data is not None:
    daily_returns = data['Close'].pct_change()
    rolling_mean = daily_returns.rolling(window=50).mean()
    rolling_std = daily_returns.rolling(window=50).std()
    z_scores = (daily_returns - rolling_mean) / rolling_std
    data.loc[z_scores.abs() > 6, 'Close'] = np.nan
    data['Close'] = data['Close'].ffill()

    data['SMA_20'] = data['Close'].rolling(window=20).mean()
    data['RSI'] = RSIIndicator(close=data['Close'], window=14).rsi()
    bb = BollingerBands(close=data['Close'], window=20, window_dev=2)
    data['BB_Lower'] = bb.bollinger_lband()
    data['BB_Upper'] = bb.bollinger_hband()
    macd_ind = MACD(close=data['Close'])
    data['MACD_Line'] = macd_ind.macd()
    data['MACD_Signal'] = macd_ind.macd_signal()

    atr_ind = AverageTrueRange(high=data['High'], low=data['Low'], close=data['Close'], window=14)
    data['ATR'] = atr_ind.average_true_range()

    def poly_forecast(prices, window=10):
        y = prices[-window:].values
        x = np.arange(len(y))
        coeffs = np.polyfit(x, y, 2)
        return np.poly1d(coeffs)(window)

    data['Poly_Forecast'] = data['Close'].rolling(window=10).apply(lambda x: poly_forecast(x))

    def generate_master_signal(row):
        forecast_move = row['Poly_Forecast'] - row['Close']
        # Connected to the slider in the sidebar!
        is_realistic = abs(forecast_move) < (row['ATR'] * atr_mult) 

        if row['Close'] <= row['BB_Lower'] and row['RSI'] < 30:
            return "🚨 STRONG BUY"
        elif row['Close'] > row['SMA_20'] and row['MACD_Line'] > row['MACD_Signal'] and is_realistic:
            return "✅ BUY (Trend + Curve)"
        elif row['Close'] < row['SMA_20']:
            return "❌ SELL (Bearish)"
        else:
            return "⏳ WAIT"

    data = data.dropna()
    data['Master_Signal'] = data.apply(generate_master_signal, axis=1)

    data['Position'] = np.where(data['Master_Signal'].str.contains("BUY"), 1, 
                                np.where(data['Master_Signal'].str.contains("SELL"), -1, 0))
    data['Stock_Return'] = data['Close'].pct_change()
    data['Strategy_Return'] = data['Stock_Return'] * data['Position'].shift(1)

    backtest_data = data.dropna().copy()
    backtest_data['Strategy_Growth'] = (1 + backtest_data['Strategy_Return']).cumprod()
    backtest_data['Market_Growth'] = (1 + backtest_data['Stock_Return']).cumprod()

    # --- 5. DASHBOARD VISUALS ---
    
    # TOP METRICS
    current = backtest_data.iloc[-1]
    strat_total = (backtest_data['Strategy_Growth'].iloc[-1] - 1) * 100
    mkt_total = (backtest_data['Market_Growth'].iloc[-1] - 1) * 100
    win_rate = (len(backtest_data[backtest_data['Strategy_Return'] > 0]) / 
                len(backtest_data[backtest_data['Strategy_Return'] != 0])) * 100

    st.subheader(f"🏆 Master Quant Report: {ticker}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Price", f"{current['Close']:.2f}")
    col2.metric("Today's Signal", current['Master_Signal'])
    col3.metric("Strategy Profit", f"{strat_total:.2f}%")
    col4.metric("Market Profit", f"{mkt_total:.2f}%")

   
# INTERACTIVE CHART SUITE (Subplots)
# 6. Plot the Zerodha-Style Intraday Subplots
    st.subheader(f"Live Intraday Terminal: {ticker} (1m Candles)")
        
        # Removed the .tail(100) so you get all 3 days of data!
    chart_live = live_data 

    fig2 = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])

        # Add Traces
    fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['Close'], mode='lines', name='Live Price', line=dict(color='black', width=2)), row=1, col=1)
    fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['Poly_Forecast'].shift(1), mode='lines', name='Forecast', line=dict(color='orange', width=2, dash='dash')), row=1, col=1)
    fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['SMA_20'], mode='lines', name='SMA 20', line=dict(color='purple', width=1.5)), row=1, col=1)

    fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['RSI'], mode='lines', name='RSI', line=dict(color='cyan', width=1.5)), row=2, col=1)
    fig2.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
    fig2.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)

    fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['MACD_Line'], mode='lines', name='MACD Line', line=dict(color='blue', width=1.5)), row=3, col=1)
    fig2.add_trace(go.Scatter(x=chart_live.index, y=chart_live['MACD_Signal'], mode='lines', name='Signal Line', line=dict(color='orange', width=1.5)), row=3, col=1)
        
    macd_hist_live = chart_live['MACD_Line'] - chart_live['MACD_Signal']
    hist_colors_live = ['rgba(0, 255, 0, 0.5)' if val >= 0 else 'rgba(255, 0, 0, 0.5)' for val in macd_hist_live]
    fig2.add_trace(go.Bar(x=chart_live.index, y=macd_hist_live, name='Histogram', marker_color=hist_colors_live), row=3, col=1)

        # --- THE GROWW/ZERODHA UPGRADES ---
        # 1. Add X and Y Axis Titles
    fig2.update_yaxes(title_text="Price (₹)", row=1, col=1)
    fig2.update_yaxes(title_text="RSI", row=2, col=1)
    fig2.update_yaxes(title_text="MACD", row=3, col=1)
    fig2.update_xaxes(title_text="Time (IST)", row=3, col=1)

        # 2. REMOVE AFTER-HOURS GAPS (Applies to all 3 subplots)
    fig2.update_xaxes(
            rangebreaks=[
                dict(bounds=["sat", "mon"]), # Hide the entire weekend
                dict(bounds=[15.5, 9.25], pattern="hour") # Hide from 3:30 PM (15.5) to 9:15 AM (9.25)
            ]
        )

        # 3. Add Interactive Time Buttons (Fixed "1d" to snap to 9:15 AM)
    fig2.update_xaxes(
            rangeslider_visible=False,
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1h", step="hour", stepmode="backward"),
                    dict(count=3, label="3h", step="hour", stepmode="backward"),
                    dict(count=1, label="1d", step="day", stepmode="todate"), # 'todate' snaps to market open!
                    dict(step="all", label="All 3 Days")
                ]),
                bgcolor="#e0e0e0", activecolor="#a0a0a0"
            ),
            row=1, col=1
        )

    fig2.update_layout(height=700, hovermode="x unified", showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)
    # 7. LIVE ACCURACY TRACKER
   # 7. LIVE ACCURACY TRACKER (VISUAL UPGRADE)
    st.markdown("---")
    st.subheader("🎯 Live Forecast Accuracy Tracker")
        
        # Grab the last 5 minutes of data
    accuracy_df = live_data[['Close', 'Poly_Forecast']].tail(5).copy()
        
        # Shift the forecast down 1 row to align with reality
    accuracy_df['What_We_Expected_Now'] = accuracy_df['Poly_Forecast'].shift(1)
    accuracy_df['Deviation (Error)'] = accuracy_df['Close'] - accuracy_df['What_We_Expected_Now']
        
    def grade_direction(row):
            if pd.isna(row['What_We_Expected_Now']): return "N/A"
            prev_close = live_data['Close'].shift(1).loc[row.name]
            actual_move = row['Close'] - prev_close
            predicted_move = row['What_We_Expected_Now'] - prev_close
            
            if (actual_move > 0 and predicted_move > 0) or (actual_move < 0 and predicted_move < 0):
                return "✅ Correct"
            else:
                return "❌ Wrong"

    accuracy_df['Direction_Grade'] = accuracy_df.apply(grade_direction, axis=1)

        # --- THE VISUAL SCORECARD ---
        # Get the absolute latest completed minute
    latest = accuracy_df.iloc[-1]
        
        # We use columns to create large "Metrics" cards instead of a boring table
    sc1, sc2, sc3, sc4 = st.columns(4)
        
    sc1.metric("Actual Price Now", f"{latest['Close']:.2f}")
    sc2.metric("What We Predicted", f"{latest['What_We_Expected_Now']:.2f}")
        
        # Show how far off the prediction was
    sc3.metric("Prediction Error", f"{latest['Deviation (Error)']:.2f} pts", delta_color="off")
        
        # Show a giant colored box for the Direction Grade
    with sc4:
            if "Correct" in str(latest['Direction_Grade']):
                st.success("**Direction: ✅ CORRECT**")
            elif "Wrong" in str(latest['Direction_Grade']):
                st.error("**Direction: ❌ WRONG**")
            else:
                st.info("Calculating...")

        # --- CLEANUP THE HISTORY TABLE ---
    with st.expander("Show Last 5 Minutes History"):
            display_acc = accuracy_df[['Close', 'What_We_Expected_Now', 'Deviation (Error)', 'Direction_Grade']].sort_index(ascending=False)
            display_acc.columns = ['Actual Price', 'Predicted 1 Min Ago', 'Point Deviation', 'Direction Grade']
            
            # Round everything to 2 decimal places so it's readable
            display_acc['Actual Price'] = display_acc['Actual Price'].round(2)
            display_acc['Predicted 1 Min Ago'] = display_acc['Predicted 1 Min Ago'].round(2)
            display_acc['Point Deviation'] = display_acc['Point Deviation'].round(2)
            
            st.dataframe(display_acc, use_container_width=True)

    # TWO-COLUMN TABLES
    st.markdown("---")
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("🎯 Forecast Grading Card")
        display_df = data[['Close', 'Poly_Forecast']].tail(10).copy()
        display_df.columns = ['Actual_Price_Today', 'Forecast_For_Tomorrow']
        display_df['What_We_Expected_Today'] = display_df['Forecast_For_Tomorrow'].shift(1)
        display_df['Forecast_Error'] = display_df['Actual_Price_Today'] - display_df['What_We_Expected_Today']

        def grade_forecast(row):
            if pd.isna(row['What_We_Expected_Today']): return "N/A"
            prev_close = data['Close'].shift(1).loc[row.name]
            actual_direction = row['Actual_Price_Today'] - prev_close
            predicted_direction = row['What_We_Expected_Today'] - prev_close
            if (actual_direction > 0 and predicted_direction > 0) or (actual_direction < 0 and predicted_direction < 0):
                return "✅ CORRECT"
            else:
                return "❌ WRONG"

        display_df['Direction_Grade'] = display_df.apply(grade_forecast, axis=1)
        # Display the dataframe in the dashboard
        st.dataframe(display_df[['Actual_Price_Today', 'What_We_Expected_Today', 'Forecast_Error', 'Direction_Grade']].sort_index(ascending=False))

    with right_col:
        st.subheader("🛡️ Daily Safety Net Inspection")
        comparison_df = data[['Close', 'Poly_Forecast', 'ATR']].tail(15).copy()
        comparison_df['Raw_Decision'] = np.where(comparison_df['Poly_Forecast'] > comparison_df['Close'], "BUY", "SELL")
        forecast_move = abs(comparison_df['Poly_Forecast'] - comparison_df['Close'])
        is_realistic = forecast_move < (comparison_df['ATR'] * atr_mult) # Connected to slider
        comparison_df['Net_Decision'] = np.where(is_realistic, comparison_df['Raw_Decision'], "⏳ WAIT")

        def get_status(row):
            if row['Raw_Decision'] != row['Net_Decision']: return "🛡️ NET ACTIVE"
            return "Normal"

        comparison_df['Safety_Status'] = comparison_df.apply(get_status, axis=1)
        # Display the dataframe in the dashboard
        st.dataframe(comparison_df[['Close', 'Raw_Decision', 'Net_Decision', 'Safety_Status']].sort_index(ascending=False))


    st.error("Could not fetch data. Please check the ticker symbol.")

  # --- 3. MANDATORY RISK DISCLAIMER ---
    st.markdown("---")
    st.caption("⚠️ **PLATFORM DISCLAIMER:** Algorithmic forecasting relies on historical data probabilities, not certainties. Financial markets are subject to extreme volatility, sudden news events, and systemic risks. This platform provides quantitative confluence tracking, NOT financial advice. Past performance and theoretical 'What If' margins guarantee no future results. You must strictly manage your own risk (using ATR Stop Losses) and consult a registered financial advisor before executing real capital trades. Trading equities algorithmically carries a high risk of capital loss.")

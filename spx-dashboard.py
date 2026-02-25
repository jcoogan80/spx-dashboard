import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings('ignore')

# Page configuration
st.set_page_config(
    page_title="S&P 500 Market Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_sp500_tickers():
    """Fetch top 50 S&P 500 companies by market cap"""
    # Manual list of top 50 S&P 500 companies by market cap (as of Feb 2025)
    # This is more reliable than scraping Wikipedia which is alphabetical
    top_50_tickers = [
        'AAPL', 'MSFT', 'NVDA', 'AMZN', 'META', 'GOOGL', 'GOOG', 'BRK.B', 
        'TSLA', 'LLY', 'AVGO', 'JPM', 'V', 'XOM', 'UNH', 'MA', 'COST', 
        'HD', 'WMT', 'PG', 'NFLX', 'JNJ', 'BAC', 'ORCL', 'CRM', 'ABBV', 
        'CVX', 'MRK', 'AMD', 'KO', 'ADBE', 'PEP', 'TMO', 'ACN', 'MCD', 
        'CSCO', 'LIN', 'ABT', 'WFC', 'PM', 'IBM', 'GE', 'ISRG', 'CAT', 
        'INTU', 'TXN', 'VZ', 'DIS', 'CMCSA', 'QCOM'
    ]
    
    # Convert to yfinance format
    tickers = [ticker.replace('.', '-') for ticker in top_50_tickers]
    
    # Try to get company names from Wikipedia for display
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        try:
            tables = pd.read_html(url, storage_options=headers)
        except:
            response = requests.get(url, headers=headers, timeout=10)
            tables = pd.read_html(response.content)
        
        sp500_table = tables[0]
        
        # Filter for our top 50 tickers
        company_df = sp500_table[sp500_table['Symbol'].isin(top_50_tickers)][['Symbol', 'Security', 'GICS Sector']]
        
        # Sort by our top 50 order
        company_df['sort_order'] = company_df['Symbol'].apply(lambda x: top_50_tickers.index(x) if x in top_50_tickers else 999)
        company_df = company_df.sort_values('sort_order').drop('sort_order', axis=1).reset_index(drop=True)
        
        return tickers, company_df
        
    except Exception as e:
        st.warning(f"Could not fetch company details: {e}")
        # Return just tickers with basic dataframe
        company_df = pd.DataFrame({
            'Symbol': top_50_tickers,
            'Security': ['Company name unavailable'] * len(top_50_tickers),
            'GICS Sector': ['N/A'] * len(top_50_tickers)
        })
        return tickers, company_df

@st.cache_data(ttl=3600)
def get_earnings_calendar_yahoo(sp500_set):
    """Scrape Yahoo Finance earnings calendar for upcoming week"""
    earnings_data = []
    today = datetime.now()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for day_offset in range(7):
        date = today + timedelta(days=day_offset)
        date_str = date.strftime('%Y-%m-%d')
        
        status_text.text(f"Fetching earnings for {date_str}...")
        progress_bar.progress((day_offset + 1) / 7)
        
        try:
            url = f"https://finance.yahoo.com/calendar/earnings?day={date_str}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                tables = pd.read_html(response.content)
                
                if tables:
                    df = tables[0]
                    if 'Symbol' in df.columns:
                        for _, row in df.iterrows():
                            ticker = row['Symbol']
                            if ticker in sp500_set:
                                # Add unique ID to prevent duplicates
                                unique_key = f"{date_str}_{ticker}"
                                if not any(e.get('unique_key') == unique_key for e in earnings_data):
                                    earnings_data.append({
                                        'unique_key': unique_key,
                                        'Date': date_str,
                                        'Ticker': ticker,
                                        'Company': row.get('Company', 'N/A'),
                                        'EPS Estimate': row.get('EPS Estimate', 'N/A'),
                                    })
        except Exception as e:
            st.warning(f"Error fetching {date_str}: {e}")
    
    progress_bar.empty()
    status_text.empty()
    
    if earnings_data:
        earnings_df = pd.DataFrame(earnings_data)
        # Remove duplicates based on Date + Ticker
        earnings_df = earnings_df.drop_duplicates(subset=['Date', 'Ticker'], keep='first')
        earnings_df = earnings_df.drop('unique_key', axis=1)
        earnings_df = earnings_df.sort_values(['Date', 'Ticker'])
        return earnings_df
    return pd.DataFrame()

def get_earnings_calendar_alphavantage(sp500_set, api_key):
    """Fetch earnings calendar using Alpha Vantage API"""
    if not api_key:
        return pd.DataFrame()
    
    try:
        url = f'https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey={api_key}'
        
        with st.spinner("Fetching earnings from Alpha Vantage..."):
            response = requests.get(url, timeout=15)
            
            # Check if response is valid
            if response.status_code != 200:
                st.error(f"API Error: Status code {response.status_code}")
                return pd.DataFrame()
            
            # Try to parse CSV
            from io import StringIO
            df = pd.read_csv(StringIO(response.text))
        
        if df.empty:
            st.error("No data returned from Alpha Vantage")
            return pd.DataFrame()
        
        # Check column names (Alpha Vantage uses lowercase)
        if 'symbol' not in df.columns:
            st.error(f"Unexpected columns from API: {df.columns.tolist()}")
            return pd.DataFrame()
        
        # Filter for S&P 500 companies (handle both formats)
        sp500_set_original = {ticker.replace('-', '.') for ticker in sp500_set}
        df = df[df['symbol'].isin(sp500_set) | df['symbol'].isin(sp500_set_original)]
        
        if df.empty:
            st.warning("No top 50 S&P 500 companies found in Alpha Vantage data")
            return pd.DataFrame()
        
        # Filter for next 7 days
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        df['reportDate'] = pd.to_datetime(df['reportDate']).dt.date
        df = df[(df['reportDate'] >= today) & (df['reportDate'] <= next_week)]
        
        if df.empty:
            st.info("No earnings in the next 7 days for top 50 companies")
            return pd.DataFrame()
        
        # Rename columns for consistency
        df = df.rename(columns={
            'symbol': 'Ticker',
            'reportDate': 'Date',
            'name': 'Company',
            'estimate': 'EPS Estimate'
        })
        
        # Convert date back to string format
        df['Date'] = df['Date'].astype(str)
        
        # Select only needed columns (in case there are extras)
        available_cols = [col for col in ['Date', 'Ticker', 'Company', 'EPS Estimate'] if col in df.columns]
        df = df[available_cols]
        
        # Remove duplicates
        df = df.drop_duplicates(subset=['Date', 'Ticker'], keep='first')
        df = df.sort_values(['Date', 'Ticker'])
        df = df.reset_index(drop=True)
        
        st.success(f"✅ Found {len(df)} earnings reports from Alpha Vantage")
        
        return df
    except Exception as e:
        st.error(f"Error fetching from Alpha Vantage: {str(e)}")
        import traceback
        st.text(traceback.format_exc())
        return pd.DataFrame()

def get_economic_calendar():
    """Scrape economic calendar from MarketWatch"""
    try:
        url = "https://www.marketwatch.com/economy-politics/calendar"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            # Try pandas read_html first
            try:
                tables = pd.read_html(response.content)
                
                if tables:
                    events = []
                    for table in tables:
                        # Look for economic calendar table structure
                        if len(table.columns) >= 3:
                            for _, row in table.iterrows():
                                try:
                                    # Try to extract event info from any table structure
                                    row_values = row.values
                                    
                                    # Skip header rows
                                    if any(isinstance(val, str) and 'Date' in str(val) for val in row_values):
                                        continue
                                    
                                    # Try to find date, time, event columns
                                    event_dict = {
                                        'Date': str(row_values[0]) if len(row_values) > 0 else 'TBD',
                                        'Time': str(row_values[1]) if len(row_values) > 1 else 'TBD',
                                        'Event': str(row_values[2]) if len(row_values) > 2 else 'Unknown',
                                        'Importance': 'Medium'  # Default
                                    }
                                    
                                    # Filter out invalid rows
                                    if event_dict['Event'] not in ['Unknown', 'nan', 'None']:
                                        events.append(event_dict)
                                except:
                                    continue
                    
                    if events:
                        df = pd.DataFrame(events)
                        # Clean up dates and remove duplicates
                        df = df.drop_duplicates(subset=['Event'], keep='first')
                        return df.head(15)  # Return first 15 events
                        
            except Exception as e:
                st.warning(f"Pandas parsing failed: {e}")
            
            # Fallback: Try BeautifulSoup parsing
            soup = BeautifulSoup(response.content, 'html.parser')
            events = []
            
            # Look for calendar tables or event listings
            calendar_tables = soup.find_all('table', class_=lambda x: x and 'calendar' in x.lower() if x else False)
            
            if not calendar_tables:
                calendar_tables = soup.find_all('table')
            
            for table in calendar_tables[:3]:  # Check first 3 tables
                rows = table.find_all('tr')
                for row in rows[1:20]:  # Skip header, get first 20 rows
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        try:
                            date_text = cols[0].get_text(strip=True)
                            event_text = cols[1].get_text(strip=True) if len(cols) > 1 else 'N/A'
                            time_text = cols[2].get_text(strip=True) if len(cols) > 2 else 'TBD'
                            
                            if event_text and event_text != 'N/A' and len(event_text) > 3:
                                events.append({
                                    'Date': date_text,
                                    'Time': time_text,
                                    'Event': event_text,
                                    'Importance': 'Medium'
                                })
                        except:
                            continue
            
            if events:
                df = pd.DataFrame(events)
                df = df.drop_duplicates(subset=['Event'], keep='first')
                return df.head(15)
            
            return pd.DataFrame()
        else:
            st.warning(f"MarketWatch returned status code: {response.status_code}")
            return pd.DataFrame()
            
    except Exception as e:
        st.warning(f"Could not scrape MarketWatch economic calendar: {e}")
        return pd.DataFrame()

def calculate_rsi(data, period=8):
    """Calculate RSI indicator"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

@st.cache_data(ttl=1800)
def get_spx_data(days):
    """Fetch SPX data for given period"""
    spx = yf.Ticker("^GSPC")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    data = spx.history(start=start_date, end=end_date)
    
    if not data.empty:
        data['RSI'] = calculate_rsi(data['Close'], period=8)
    
    return data

def plot_spx_chart(data, period_name):
    """Create SPX candlestick and RSI charts"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # Candlestick chart
    # Calculate colors for each candle
    colors = ['g' if close >= open_ else 'r' 
              for close, open_ in zip(data['Close'], data['Open'])]
    
    # Plot candlesticks
    for idx, (date, row) in enumerate(data.iterrows()):
        # Draw the high-low line (wick)
        ax1.plot([date, date], [row['Low'], row['High']], 
                color='black', linewidth=0.5, zorder=1)
        
        # Draw the open-close rectangle (body)
        height = abs(row['Close'] - row['Open'])
        bottom = min(row['Open'], row['Close'])
        color = 'green' if row['Close'] >= row['Open'] else 'red'
        
        ax1.add_patch(plt.Rectangle((date, bottom), 
                                    timedelta(hours=12), height,
                                    facecolor=color, edgecolor='black',
                                    linewidth=0.5, zorder=2))
    
    ax1.set_title(f'SPX - Last {period_name} (Candlestick)', fontsize=14, fontweight='bold', pad=10)
    ax1.set_ylabel('Price (USD)', fontsize=11, labelpad=8)
    ax1.grid(True, alpha=0.3, zorder=0)
    ax1.xaxis.set_major_locator(plt.MaxNLocator(8))
    
    # Stats
    current_price = data['Close'].iloc[-1]
    period_high = data['High'].max()
    period_low = data['Low'].min()
    period_return = ((current_price - data['Close'].iloc[0]) / data['Close'].iloc[0]) * 100
    
    text_str = f'Current: ${current_price:.2f}\nHigh: ${period_high:.2f}\nLow: ${period_low:.2f}\nReturn: {period_return:+.2f}%'
    ax1.text(0.02, 0.98, text_str, transform=ax1.transAxes, 
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
            fontsize=10)
    
    # RSI chart
    ax2.plot(data.index, data['RSI'], linewidth=2, color='#A23B72', label='RSI (8)')
    ax2.axhline(y=70, color='r', linestyle='--', linewidth=1, alpha=0.7, label='Overbought (70)')
    ax2.axhline(y=30, color='g', linestyle='--', linewidth=1, alpha=0.7, label='Oversold (30)')
    ax2.fill_between(data.index, 30, 70, alpha=0.1, color='gray')
    ax2.set_title(f'8-Day RSI - Last {period_name}', fontsize=14, fontweight='bold', pad=10)
    ax2.set_xlabel('Date', fontsize=11, labelpad=8)
    ax2.set_ylabel('RSI', fontsize=11, labelpad=8)
    ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper left', fontsize=9)
    ax2.xaxis.set_major_locator(plt.MaxNLocator(8))
    
    # RSI status
    current_rsi = data['RSI'].iloc[-1]
    if current_rsi > 70:
        rsi_status = 'Overbought'
    elif current_rsi < 30:
        rsi_status = 'Oversold'
    else:
        rsi_status = 'Neutral'
    
    rsi_text = f'Current RSI: {current_rsi:.2f}\nStatus: {rsi_status}'
    ax2.text(0.02, 0.98, rsi_text, transform=ax2.transAxes,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5),
            fontsize=10)
    
    plt.tight_layout()
    return fig

# Main App
def main():
    st.title("📈 S&P 500 Market Dashboard")
    st.markdown("### Real-time analysis of top 50 S&P 500 companies")
    
    # Sidebar
    st.sidebar.header("⚙️ Settings")
    
    # Alpha Vantage API Key input
    st.sidebar.subheader("Earnings Calendar Data Source")
    use_alphavantage = st.sidebar.checkbox("Use Alpha Vantage API (more accurate)", value=False)
    
    alphavantage_key = ""
    if use_alphavantage:
        alphavantage_key = st.sidebar.text_input(
            "Alpha Vantage API Key",
            type="password",
            help="Get free API key at: https://www.alphavantage.co/support/#api-key"
        )
        st.sidebar.markdown("[Get free API key](https://www.alphavantage.co/support/#api-key) (25 calls/day)")
    
    st.sidebar.markdown("---")
    
    # Time period selector
    time_periods = {
        'Week': 7,
        'Month': 30,
        '3 Months': 90,
        '6 Months': 180,
        'Year': 365
    }
    
    selected_period = st.sidebar.selectbox(
        "Select Time Period",
        options=list(time_periods.keys()),
        index=1  # Default to Month
    )
    
    show_earnings = st.sidebar.checkbox("Show Earnings Calendar", value=True)
    show_company_list = st.sidebar.checkbox("Show Top 50 Companies", value=False)
    
    if st.sidebar.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Main content
    with st.spinner("Loading S&P 500 data..."):
        tickers, company_df = get_sp500_tickers()
    
    if not tickers:
        st.error("Failed to load S&P 500 tickers. Please try again.")
        return
    
    st.success(f"✅ Loaded top {len(tickers)} S&P 500 companies by market cap")
    
    # Show company list if requested
    if show_company_list:
        with st.expander("📋 Top 50 S&P 500 Companies", expanded=False):
            st.dataframe(company_df, use_container_width=True)
    
    # Earnings Calendar Section
    if show_earnings:
        st.markdown("---")
        st.header("📅 Upcoming Earnings Calendar")
        
        if use_alphavantage and alphavantage_key:
            st.markdown("*Using Alpha Vantage API - Next 7 days for top 50 S&P 500 companies*")
            with st.spinner("Fetching earnings from Alpha Vantage..."):
                sp500_set = set(tickers)
                earnings_df = get_earnings_calendar_alphavantage(sp500_set, alphavantage_key)
        else:
            st.markdown("*Using Yahoo Finance web scraping - Next 7 days for top 50 S&P 500 companies*")
            st.info("⚠️ Note: Yahoo Finance scraping can be unreliable and may show duplicate/stale data. For accurate earnings, enable Alpha Vantage API in the sidebar (free tier available).")
            with st.spinner("Fetching earnings calendar..."):
                sp500_set = set(tickers)
                earnings_df = get_earnings_calendar_yahoo(sp500_set)
        
        if not earnings_df.empty:
            # Summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Earnings Reports", len(earnings_df))
            with col2:
                unique_dates = earnings_df['Date'].nunique()
                st.metric("Trading Days", unique_dates)
            with col3:
                today_earnings = len(earnings_df[earnings_df['Date'] == datetime.now().strftime('%Y-%m-%d')])
                st.metric("Today's Reports", today_earnings)
            
            # Earnings by day
            st.subheader("Earnings by Date")
            for date in sorted(earnings_df['Date'].unique()):
                with st.expander(f"📆 {date} ({len(earnings_df[earnings_df['Date'] == date])} companies)"):
                    day_df = earnings_df[earnings_df['Date'] == date][['Ticker', 'Company', 'EPS Estimate']]
                    st.dataframe(day_df, use_container_width=True, hide_index=True)
            
            # Full table
            with st.expander("📊 Full Earnings Table", expanded=False):
                st.dataframe(earnings_df, use_container_width=True, hide_index=True)
        else:
            st.info("No earnings found for top 50 companies in the next 7 days, or unable to fetch data.")
            st.markdown("**Alternative sources:**")
            st.markdown("- [Yahoo Finance](https://finance.yahoo.com/calendar/earnings)")
            st.markdown("- [MarketWatch](https://www.marketwatch.com/tools/earnings-calendar)")
    
    # Economic Calendar Info
    st.markdown("---")
    st.header("📊 Economic Calendar - This Week")
    
    # Manual key events section
    st.subheader("🔔 Key Events This Week")
    
    # Editable events - UPDATE THIS SECTION WEEKLY
    key_events = [
        {"Date": "2025-02-25", "Time": "9:00 PM EST", "Event": "State of the Union Address", "Importance": "High"},
        {"Date": "2025-02-26", "Time": "8:30 AM EST", "Event": "Durable Goods Orders (MoM)", "Importance": "Medium"},
        {"Date": "2025-02-27", "Time": "10:00 AM EST", "Event": "Consumer Confidence Index", "Importance": "High"},
        {"Date": "2025-02-28", "Time": "8:30 AM EST", "Event": "GDP Growth Rate (QoQ)", "Importance": "High"},
        {"Date": "2025-02-28", "Time": "10:00 AM EST", "Event": "Fed Chair Powell Speech", "Importance": "High"},
        # ADD MORE EVENTS HERE - Copy format above
    ]
    
    # Display events
    events_df = pd.DataFrame(key_events)
    events_df = events_df.sort_values('Date')
    
    # Color code by importance
    def highlight_importance(row):
        if row['Importance'] == 'High':
            return ['background-color: #ffcccc'] * len(row)
        elif row['Importance'] == 'Medium':
            return ['background-color: #fff4cc'] * len(row)
        else:
            return [''] * len(row)
    
    styled_df = events_df.style.apply(highlight_importance, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
    st.info("💡 **To update events:** Edit the `key_events` list in the code (lines ~570-577)")
    
    # Summary
    high_events = len(events_df[events_df['Importance'] == 'High'])
    st.success(f"📌 {high_events} high-impact events this week")
    
    st.markdown("---")
    
    # Try to fetch from MarketWatch (optional/supplementary)
    with st.expander("📰 Additional Economic Data (Live from MarketWatch)", expanded=False):
        with st.spinner("Attempting to fetch from MarketWatch..."):
            econ_df = get_economic_calendar()
        
        if not econ_df.empty:
            st.dataframe(econ_df, use_container_width=True, hide_index=True)
            st.success(f"✅ Found {len(econ_df)} events from MarketWatch")
        else:
            st.warning("⚠️ Unable to fetch from MarketWatch (site may be blocking or using JavaScript)")
        
    with st.expander("ℹ️ Economic Calendar Resources", expanded=False):
        st.markdown("""
        **Major Economic Indicators to Watch:**
        - Federal Reserve announcements and FOMC minutes
        - Employment reports (Non-Farm Payrolls, Unemployment Rate)
        - Inflation data (CPI, PPI)
        - GDP reports
        - Consumer confidence indices
        - PMI (Purchasing Managers' Index) reports
        - Political events (State of the Union, G7 meetings, etc.)
        """)
        
        st.markdown("**Live Calendar Sources:**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("[Investing.com Calendar](https://www.investing.com/economic-calendar/)")
        with col2:
            st.markdown("[Trading Economics](https://tradingeconomics.com/calendar)")
        with col3:
            st.markdown("[FRED Economic Data](https://fred.stlouisfed.org)")
    
    # SPX Charts Section
    st.markdown("---")
    st.header(f"📈 S&P 500 (SPX) - {selected_period} Analysis")
    
    with st.spinner(f"Loading {selected_period} data..."):
        days = time_periods[selected_period]
        spx_data = get_spx_data(days)
    
    if not spx_data.empty:
        # Display metrics
        current_price = spx_data['Close'].iloc[-1]
        prev_price = spx_data['Close'].iloc[0]
        price_change = current_price - prev_price
        price_change_pct = (price_change / prev_price) * 100
        current_rsi = spx_data['RSI'].iloc[-1]
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Current Price", f"${current_price:.2f}", f"{price_change:+.2f} ({price_change_pct:+.2f}%)")
        with col2:
            st.metric("Period High", f"${spx_data['Close'].max():.2f}")
        with col3:
            st.metric("Period Low", f"${spx_data['Close'].min():.2f}")
        with col4:
            rsi_delta = "Overbought" if current_rsi > 70 else "Oversold" if current_rsi < 30 else "Neutral"
            st.metric("RSI (8-day)", f"{current_rsi:.2f}", rsi_delta)
        
        # Plot chart
        fig = plot_spx_chart(spx_data, selected_period)
        st.pyplot(fig)
        plt.close()
        
        # Option to view all periods
        if st.checkbox("Show All Time Periods"):
            st.subheader("All Time Period Comparison")
            tabs = st.tabs(list(time_periods.keys()))
            
            for idx, (period_name, days) in enumerate(time_periods.items()):
                with tabs[idx]:
                    period_data = get_spx_data(days)
                    if not period_data.empty:
                        fig = plot_spx_chart(period_data, period_name)
                        st.pyplot(fig)
                        plt.close()
    else:
        st.error("Unable to load SPX data. Please try again.")
    
    # Footer
    st.markdown("---")
    st.markdown("*Data sources: Yahoo Finance, Wikipedia. Updates hourly. Not financial advice.*")

if __name__ == "__main__":
    main()

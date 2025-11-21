import MetaTrader5 as mt5
from telethon import TelegramClient, events
import re
import logging

# --- CONFIG --- (edit these for your account)
api_id = 39024955
api_hash = 'fb1c3b3a2fd0ed0a6e1a49bdc67ab1e2'
bot_token = '7832217673:AAFixQQ69sPzJ6fFLgod1-i8Fv6PfZKb-8w'
signal_channel = -1003335063734
MT5_LOGIN = 25761651
MT5_PASSWORD = 'ubxjNQNI_-55'
MT5_SERVER = 'FivePercentOnline-Real'
LOT_SIZE = 0.15

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('mt5_signal_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def parse_signal(message):
    action_match = re.search(r'^(BUY|SELL)\s+([A-Z]+)\s+([\d\.]+)', message, re.MULTILINE | re.IGNORECASE)
    tp2 = re.search(r'🤑TP2:\s*([\d\.]+)', message)
    sl = re.search(r'🔴SL:\s*([\d\.]+)', message)
    if action_match and tp2 and sl:
        action, symbol, entry = action_match.groups()
        signal = {
            'action': action.upper(),
            'symbol': symbol,
            'entry': float(entry),
            'tp': float(tp2.group(1)),
            'sl': float(sl.group(1))
        }
        logging.info(f"Parsed signal: {signal}")
        return signal
    return None

def connect_mt5():
    status = mt5.initialize(server=MT5_SERVER, login=MT5_LOGIN, password=MT5_PASSWORD)
    if not status:
        logging.error(f"MT5 initialization failed with error code: {mt5.last_error()}")
    return status

def open_trade(signal):
    if not connect_mt5():
        logging.error('Could not connect to MT5')
        return

    symbol_info = mt5.symbol_info(signal['symbol'])
    if not symbol_info:
        logging.error(f"Symbol {signal['symbol']} not found.")
        mt5.shutdown()
        return
    if not symbol_info.visible:
        mt5.symbol_select(signal['symbol'], True)

    # Debug info (note: stops_level is plural here)
    logging.info(f"SymbolInfo: stops_level={symbol_info.stops_level}, tick_size={symbol_info.tick_size}, volume_min={symbol_info.volume_min}, volume_max={symbol_info.volume_max}")
    logging.info(f"Order price request: entry={signal['entry']}, SL={signal['sl']}, TP={signal['tp']}, lot={LOT_SIZE}")

    order_type = mt5.ORDER_TYPE_BUY if signal['action'] == 'BUY' else mt5.ORDER_TYPE_SELL
    price = mt5.symbol_info_tick(signal['symbol']).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(signal['symbol']).bid

    # Check STOPLEVEL rule: SL/TP must be at least symbol_info.stops_level * symbol_info.tick_size away
    stops_level = symbol_info.stops_level * symbol_info.tick_size

    if order_type == mt5.ORDER_TYPE_BUY:
        if (signal['sl'] >= price or price >= signal['tp'] or (price - signal['sl']) < stops_level or (signal['tp'] - price) < stops_level):
            logging.error(f"Invalid stops for BUY: SL or TP too close to price (required min distance {stops_level})")
            mt5.shutdown()
            return
    else:
        if (signal['sl'] <= price or price <= signal['tp'] or (signal['sl'] - price) < stops_level or (price - signal['tp']) < stops_level):
            logging.error(f"Invalid stops for SELL: SL or TP too close to price (required min distance {stops_level})")
            mt5.shutdown()
            return

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": signal['symbol'],
        "volume": LOT_SIZE,
        "type": order_type,
        "price": price,
        "sl": signal['sl'],
        "tp": signal['tp'],
        "deviation": 10,
        "magic": 987654,
        "comment": "Signal opened at TP2",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    logging.info(f"OPEN TRADE result: {result}")
    mt5.shutdown()

def close_positions(symbol):
    if not connect_mt5():
        logging.error('Could not reconnect to MT5 for closing.')
        return

    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        logging.info(f"No open positions to close for {symbol}")
        mt5.shutdown()
        return
    for pos in positions:
        close_type = mt5.ORDER_TYPE_BUY if pos.type == mt5.ORDER_TYPE_SELL else mt5.ORDER_TYPE_SELL
        price = mt5.symbol_info_tick(symbol).ask if close_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 10,
            "magic": 987654,
            "comment": "Closed by TP2 message",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(close_request)
        logging.info(f"CLOSE POSITION result: {result}")
    mt5.shutdown()

def tp2_message_detected(message):
    return "TP2 hit" in message or "CLOSE HERE NOW" in message

def main():
    logging.info("Bot started — initializing…")
    client = TelegramClient('mt5_signal_session', api_id, api_hash).start(bot_token=bot_token)
    logging.info("Telegram client started and waiting for messages…")

    @client.on(events.NewMessage(chats=(signal_channel,)))
    async def handler(event):
        text = event.text
        logging.info(f"NEW MESSAGE: {text}")
        signal = parse_signal(text)
        if signal:
            logging.info("Opening trade (TP2 target)…")
            open_trade(signal)
        elif tp2_message_detected(text):
            logging.info("TP2 message detected, closing all open trades for symbol XAUUSD")
            close_positions('XAUUSD')
        else:
            logging.info("Message ignored.")

    logging.info("Bot is now running.")
    client.run_until_disconnected()

if __name__ == "__main__":
    main()

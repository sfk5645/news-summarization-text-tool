#import requests
from requests_oauthlib import OAuth1Session
import os
import pyetrade
from dotenv import load_dotenv

load_dotenv()

E_TRADE_API_KEY = os.getenv("E_TRADE_API_KEY")
E_TRADE_API_SECRET = os.getenv("E_TRADE_API_SECRET")
E_TRADE_TOKEN = os.getenv("E_TRADE_TOKEN")
E_TRADE_TOKEN_SECRET = os.getenv("E_TRADE_TOKEN_SECRET")

def get_portfolio_ticket_symbols():

    #Code to generate token and secret. This can be added to your env after.
    #Lib Docs: http://github.com/jessecooper/pyetrade?tab=readme-ov-file
    """oauth = pyetrade.ETradeOAuth(E_TRADE_API_KEY, E_TRADE_API_SECRET)
    print(oauth.get_request_token()) 
    verifier_code = input("Enter verification code: ")
    tokens = oauth.get_access_token(verifier_code)
    print(tokens)"""
    #tokens = {'oauth_token' : tokens["oauth_token"],'oauth_token_secret' : tokens["oauth_token_secret"]}
    """accounts = pyetrade.ETradeAccounts(
        E_TRADE_API_KEY,
        E_TRADE_API_SECRET,
        E_TRADE_TOKEN,
        E_TRADE_TOKEN_SECRET,
        dev=False
    )
    accounts_dict = accounts.list_accounts()
    for account_dict in accounts_dict['AccountListResponse']['Accounts']['Account']:
        if account_dict['institutionType'] == 'BROKERAGE':
            print(account_dict['accountIdKey'])
            #print(accounts.get_account_portfolio(account_dict['accountIdKey']))"""


    
    """auth = OAuth1Session(E_TRADE_API_KEY, E_TRADE_API_SECRET, E_TRADE_REQUEST_TOKEN, E_TRADE_REQUEST_TOKEN_SECRET)
    req = auth.get(accounts_url)
    print(req)"""
    return ["AAPL", "AMD", "AMZN", "BULL", "FBIO", "GOOGL", "GPUS", "LAES", "MSFT", "NVDA", "PLTR", "PLUG", "QQQ", "TSLA", "TSM", "UAVS"]

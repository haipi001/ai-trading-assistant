"""Account market metadata shared by workspace selection and research reads."""
def account_markets(account):
    return {'brokerage':['stocks'],'broker':['stocks'],'exchange':['cex'],
            'exchange_account':['cex'],'crypto_exchange':['cex']}.get(account.account_type,[])

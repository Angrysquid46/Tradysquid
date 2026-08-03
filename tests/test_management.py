from datetime import datetime,timezone,timedelta
from tradysquid.trading.management import evaluate_management
CFG={'management':{'hard_stop_pct':.15,'profit_target_pct':.2,'break_even_activation_pct':.1,'trailing_activation_pct':.15,'maximum_mfe_giveback_pct':.05}}
def test_target_and_stop():
    assert evaluate_management({'pnl_pct':.21,'mfe_pct':.21},CFG).action=='EXIT'
    assert evaluate_management({'pnl_pct':-.16,'mfe_pct':0},CFG).reason=='hard stop reached'
def test_trailing_protects_profit():
    d=evaluate_management({'pnl_pct':.09,'mfe_pct':.16},CFG); assert d.action=='EXIT' and 'giveback' in d.reason
def test_break_even_state():
    cfg={'management':{**CFG['management'],'trailing_activation_pct':None,'maximum_mfe_giveback_pct':None}}
    assert evaluate_management({'pnl_pct':.05,'mfe_pct':.11},cfg).next_state=='PROFIT_PROTECTED'

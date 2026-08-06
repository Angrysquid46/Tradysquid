from tradysquid.learning.metrics import calculate,sample_label
def test_sample_labels(): assert sample_label(0)=='INSUFFICIENT SAMPLE' and sample_label(10)=='EARLY SAMPLE' and sample_label(30)=='DESCRIPTIVE COMPARISON AVAILABLE'
def test_metrics():
    m=calculate([{'pnl_dollars':10},{'pnl_dollars':-5}]); assert m['win_rate']==.5; assert m['expectancy']==2.5; assert m['profit_factor']==2

-- Maps the statement line items we care about onto the XBRL tags companies
-- actually use. Filers are not consistent: Apple switched revenue tags in
-- 2018, banks report RevenuesNetOfInterestExpense, and some filers use
-- ProfitLoss where others use NetIncomeLoss, and SalesRevenueGoodsNet was the
-- standard revenue tag for goods companies until ASC 606 retired it in 2018.
-- Priority resolves collisions
-- when a filer reports more than one tag for the same concept and period
-- (lower wins).
SELECT concept, tag, priority
FROM (VALUES
    ('revenue',             'Revenues',                                                               1),
    ('revenue',             'RevenueFromContractWithCustomerExcludingAssessedTax',                    2),
    ('revenue',             'SalesRevenueNet',                                                        3),
    ('revenue',             'RevenuesNetOfInterestExpense',                                           4),
    ('revenue',             'SalesRevenueGoodsNet',                                                   5),
    ('operating_income',    'OperatingIncomeLoss',                                                    1),
    ('net_income',          'NetIncomeLoss',                                                          1),
    ('net_income',          'ProfitLoss',                                                             2),
    ('total_assets',        'Assets',                                                                 1),
    ('total_equity',        'StockholdersEquity',                                                     1),
    ('total_equity',        'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest', 2),
    ('cash',                'CashAndCashEquivalentsAtCarryingValue',                                  1),
    ('long_term_debt',      'LongTermDebtNoncurrent',                                                 1),
    ('long_term_debt',      'LongTermDebt',                                                           2),
    ('operating_cash_flow', 'NetCashProvidedByUsedInOperatingActivities',                             1),
    ('capex',               'PaymentsToAcquirePropertyPlantAndEquipment',                             1),
    ('capex',               'PaymentsToAcquireProductiveAssets',                                      2)
) AS t(concept, tag, priority)

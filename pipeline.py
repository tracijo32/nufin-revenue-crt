from config import Config
from data import complete_chart_string_mapping, \
    BlackthornData, MembershipData, StripeData
import match
import aggregate as agg
import pandas as pd
import os

def run_pipeline(
    config: Config
) -> tuple[BlackthornData, MembershipData, StripeData]:

    ## load in the transaction data from each source
    bt_data = config.load_blackthorn_data()
    mbr_data = config.load_membership_data()
    stripe_data = config.load_stripe_data()

    ## dump the raw data to a csv, so you can see what it looks like unprocessed
    data_path = os.path.join(config.output_path,'data')
    os.makedirs(data_path,exist_ok=True)
    bt_data.dump_data(os.path.join(data_path,'raw_blackthorn_data.csv'))
    mbr_data.dump_data(os.path.join(data_path,'raw_membership_data.csv'))
    stripe_data.dump_data(os.path.join(data_path,'stripe_data.csv'))

    #########################################################
    ### clean the data
    #########################################################

    ## load in the chart string mapping and apply it to the data
    cs_map_df = config.load_chart_string_mapping()
    full_cs_map_df = complete_chart_string_mapping(
        bt_data.invoices,
        bt_data.items,
        mbr_data.memberships,
        cs_map_df
    )
    bt_data.apply_chart_string_overrides(full_cs_map_df)
    mbr_data.apply_chart_string_overrides(full_cs_map_df)

    ## if the config is set to zero out discounts, do so
    if config.set_discounts_to_zero:
        bt_data.items.loc[bt_data.items['total'].lt(0),'total'] = 0

    ## apply the line item overrides to the data
    bt_data.apply_line_item_overrides(config.load_line_item_override())

    ## dump the processed data to a csv, so you can see what it looks like processed
    bt_data.dump_data(os.path.join(data_path,'processed_blackthorn_data.csv'))
    mbr_data.dump_data(os.path.join(data_path,'processed_membership_data.csv'))

    #########################################################
    ### match the transactions
    #########################################################
    qc_path = os.path.join(config.output_path,'quality_control')
    os.makedirs(qc_path,exist_ok=True)

    refund_df = match.match_refunds(bt_data, stripe_data, config)

    ## dump the matched data to a csv, so you can see what it looks like matched
    refund_df.to_csv(os.path.join(qc_path,'matched_refunds.csv'),index=False)

    bt_match_df, mbr_match_df = match.match_charges(stripe_data, bt_data, mbr_data)

    ## dump the matched data to a csv, so you can see what it looks like matched
    bt_match_df.to_csv(os.path.join(qc_path,'matched_blackthorn_data.csv'),index=False)
    mbr_match_df.to_csv(os.path.join(qc_path,'matched_membership_data.csv'),index=False)

    #########################################################
    ### aggregate the data
    #########################################################

    ## aggregate the blackthorn data
    bt_gross, bt_fees = agg.aggregate_blackthorn(bt_match_df, bt_data, config)

    ## aggregate the membership data
    mbr_gross, mbr_fees = agg.aggregate_memberships(mbr_match_df, config)

    gross_df = pd.concat([bt_gross,mbr_gross])
    fees_df = pd.concat([bt_fees,mbr_fees])

    chg_bal = agg.balance_charges(stripe_data,gross_df,fees_df)
    chg_bal.to_csv(os.path.join(qc_path,'balanced_charges.csv'),index=False)

    ## balance the refunds
    ref_bal = agg.balance_refunds(stripe_data,refund_df)
    ref_bal.to_csv(os.path.join(qc_path,'balanced_refunds.csv'),index=False)

    ## aggregate the usage fees
    usage_df = agg.aggregate_usage_fees(stripe_data, config)

    #########################################################
    crt_path = os.path.join(config.output_path,'crt')
    os.makedirs(crt_path,exist_ok=True)

    ## get the crt lines
    crt_lines = agg.get_crt_lines(gross_df, fees_df, refund_df, usage_df, config)

    ## dump the crt lines to a csv, so you can see what it looks like
    crt_lines.to_csv(os.path.join(crt_path,'crt_lines.csv'),index=False)

    ## balance the crt
    crt_bal = agg.balance_crt(stripe_data, crt_lines)
    crt_bal.to_csv(os.path.join(qc_path,'balanced_crt.csv'),index=False)

    return crt_lines, crt_bal, chg_bal, ref_bal

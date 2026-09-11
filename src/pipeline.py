from config import Config
from data import BlackthornData, MembershipData, StripeData
import match
import aggregate as agg
import pandas as pd
import os
from tqdm import tqdm
from output import generate_daily_gateway_output_file

def run_pipeline(
    config: Config
) -> tuple[BlackthornData, MembershipData, StripeData]:

    print('Running daily reconciliation pipeline')

    ## load in the transaction data from each source
    print('Loading blackthorn data...', end='')
    bt_data = config.load_blackthorn_data()
    print('done')
    print('Loading membership data...', end='')
    mbr_data = config.load_membership_data()
    print('done')
    print('Loading stripe data...', end='')
    stripe_data = config.load_stripe_data()
    print('done')

    ## dump the raw data to a csv, so you can see what it looks like unprocessed
    data_path = os.path.join(config.output_path,'data')
    os.makedirs(data_path,exist_ok=True)
    print('Dumping raw data to csv...', end='')
    bt_data.dump_data(os.path.join(data_path,'raw_blackthorn_data.csv'))
    mbr_data.dump_data(os.path.join(data_path,'raw_membership_data.csv'))
    stripe_data.dump_data(os.path.join(data_path,'stripe_data.csv'))
    print('done, files saved to', data_path)

    #########################################################
    ### clean the data
    #########################################################
    print('Cleaning data and applying overrides....', end='')
    ## load in the chart string mapping and apply it to the data
    full_cs_map_df = match.complete_chart_string_mapping(
        blackthorn_data=bt_data,
        membership_data=mbr_data,
        config=config
    )
    bt_data.apply_chart_string_overrides(full_cs_map_df)
    mbr_data.apply_chart_string_overrides(full_cs_map_df)

    ## if the config is set to zero out discounts, do so
    if config.set_discounts_to_zero:
        bt_data.items.loc[bt_data.items['total'].lt(0),'total'] = 0

    ## apply the line item overrides to the data
    bt_data.apply_line_item_overrides(config.load_line_item_override())
    print('done')

    print('Dumping processed data to csv...', end='')
    ## dump the processed data to a csv, so you can see what it looks like processed
    bt_data.dump_data(os.path.join(data_path,'processed_blackthorn_data.csv'))
    mbr_data.dump_data(os.path.join(data_path,'processed_membership_data.csv'))
    print('done, files saved to', data_path)

    #########################################################
    ### match the transactions
    #########################################################
    print('Matching blackthorn and membership transactions to stripe transactions...', end='')
    refund_df = match.match_refunds(bt_data, stripe_data, config)

    ## dump the matched data to a csv, so you can see what it looks like matched
    refund_df.to_csv(os.path.join(config.output_path,'matched_refunds.csv'),index=False)

    bt_match_df, mbr_match_df = match.match_charges(stripe_data, bt_data, mbr_data)

    ## dump the matched data to a csv, so you can see what it looks like matched
    bt_match_df.to_csv(
        os.path.join(config.output_path,'matched_blackthorn.csv'),
        index=False,
        date_format='%m/%d/%Y'
    )
    mbr_match_df.to_csv(
        os.path.join(config.output_path,'matched_membership.csv'),
        index=False,
        date_format='%Y-%m-%d'
    )
    print('done, matched files saved to', config.output_path)

    #########################################################
    ### aggregate the data
    #########################################################
    print('Aggregating data...', end='')
    ## aggregate the blackthorn data
    bt_gross, bt_fees = agg.aggregate_blackthorn(bt_match_df, bt_data, config)

    ## aggregate the membership data
    mbr_gross, mbr_fees = agg.aggregate_memberships(mbr_match_df, config)

    gross_df = pd.concat([bt_gross,mbr_gross])
    fees_df = pd.concat([bt_fees,mbr_fees])

    chg_bal = agg.balance_charges(stripe_data,gross_df,fees_df)
    chg_bal.to_csv(
        os.path.join(config.output_path,'balanced_charges.csv'),
        index=False,
        date_format='%m/%d/%Y'
    )

    ## balance the refunds
    ref_bal = agg.balance_refunds(stripe_data,refund_df)
    ref_bal.to_csv(
        os.path.join(config.output_path,'balanced_refunds.csv'),
        index=False,
        date_format='%m/%d/%Y'
    )

    ## aggregate the usage fees
    usage_df = agg.aggregate_usage_fees(stripe_data, config)
    print('done')
    #########################################################
    ## get the crt lines
    crt_lines = agg.get_crt_lines(gross_df, fees_df, refund_df, usage_df)

    ## dump the crt lines to a csv, so you can see what it looks like
    crt_lines.to_csv(os.path.join(config.output_path,'crt_lines.csv'),index=False)

    ## balance the crt
    crt_bal = agg.balance_crt(crt_lines, stripe_data)
    crt_bal.to_csv(os.path.join(config.output_path,'balanced_crt.csv'),index=False)

    daily_path = os.path.join(config.output_path,'daily_reconcilation')
    os.makedirs(daily_path,exist_ok=True)

    ## output the daily reconciliation files
    daily = crt_bal[['gateway','wire_date']].drop_duplicates()
    for gateway, wire_date in tqdm(
        daily.itertuples(index=False), 
        total=len(daily), 
        desc='Generating daily reconciliation files'):
        generate_daily_gateway_output_file(
            wire_date=wire_date,
            gateway=gateway,
            path_to_output=daily_path,
            crt_lines=crt_lines,
            crt_bal=crt_bal,
            mbr_match_df=mbr_match_df,
            bt_match_df=bt_match_df,
            bt_data=bt_data,
            refund_df=refund_df
        )
    print('Reconciliation complete. Daily files saved to', daily_path)

# functions to check validity of forcing and state DataFrames
# import yaml
# yaml.warnings({'YAMLLoadWarning': False})
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from ._env import logger_supy, trv_supy_module, trv_supy_module
from ._load import dict_var_type_forcing, set_var_use


# the check list file with ranges and logics
# path_rules_indiv = path_supy_module / "checker_rules_indiv.json"
path_rules_indiv = trv_supy_module.joinpath("checker_rules_indiv.json")


# opening the check list file
def load_rules(path_rules) -> Dict:
    with open(path_rules) as cf:
        dict_rules = json.load(cf)

    # making the keys lowercase to be consistent with supy
    dict_rules_lower = {}
    for key in dict_rules.keys():
        # for some reason pop() did not work here!!
        dict_rules_lower[key.lower()] = dict_rules[key]

    return dict_rules_lower


# store rules as a dict
dict_rules_indiv = load_rules(path_rules_indiv)


# checking the range of each parameter
def check_range(ser_to_check: pd.Series, rule_var: dict) -> Tuple:
    var = ser_to_check.name.lower()

    min_v = rule_var[var]["param"]["min"]
    max_v = rule_var[var]["param"]["max"]
    min_v = -np.inf if isinstance(min_v, str) else min_v
    max_v = np.inf if isinstance(max_v, str) else max_v
    description = ""
    is_accepted_flag = True
    try:
        flag_optional = rule_var[var]["optional"]
    except KeyError:
        flag_optional = True

    # if the parameter is optional and not set, it is accepted
    ser_to_check_nan = ser_to_check.replace(-999.0, np.nan)
    if flag_optional:
        ser_to_check_nan = ser_to_check_nan.dropna()
    ser_flag = ~ser_to_check_nan.between(min_v, max_v)
    n_flag = ser_flag.sum()
    if ser_flag.sum() > 0:
        is_accepted_flag = False
        ind = ser_flag.index[ser_flag]
        ind = [ser_flag.index.get_loc(x) for x in ind]
        description = f"`{var}` should be between [{min_v}, {max_v}] but {n_flag} outliers are found at:\n {ind}"

    if not is_accepted_flag:
        is_accepted = is_accepted_flag
        suggestion = "change the parameter to fall into the acceptable range"
    else:
        is_accepted = is_accepted_flag
        suggestion = ""

    return var, is_accepted, description, suggestion


def check_zd_zh(var, values, cr):
    return 0


# check if a valid method is set
def check_method(ser_to_check: pd.Series, rule_var: dict) -> Tuple:
    var = ser_to_check.name.lower()

    list_val = rule_var[var]["param"]["allowed"]
    description = ""

    is_accepted_flag = False
    for value in np.nditer(ser_to_check.values):
        if value in list_val:
            is_accepted_flag = True
        else:
            description = f"`{var}` should be one of {list_val} but is set as `{value}`"

    if not is_accepted_flag:
        is_accepted = is_accepted_flag
        suggestion = "change the parameter to an allowed value"
    else:
        is_accepted = is_accepted_flag
        suggestion = ""

    return var, is_accepted, description, suggestion


# # checks for suews parameters
# def check_var_suews(var, values, cr, df_sum):

#     logic = cr[var]['logic']

#     if logic == 'range':
#         out_list = check_range(var, values, cr)
#     elif logic == 'zd-zh':
#         out_list = check_zd_zh(var, values, cr)

#     df_sum.loc[len(df_sum)] = out_list

#     return df_sum
list_col_forcing = list(dict_var_type_forcing.keys())


def check_forcing(df_forcing: pd.DataFrame, fix=False):
    if fix:
        df_forcing_fix = df_forcing.copy()
    logger_supy.info("SuPy is validating `df_forcing`...")
    # collect issues
    list_issues = []
    flag_valid = True
    # check the following:
    # 1. correct columns
    col_df = df_forcing.columns
    # 1.1 if all columns are present
    set_diff = set(list_col_forcing).difference(col_df)
    if len(set_diff) > 0:
        str_issue = f"Missing columns found: {set_diff}"
        list_issues.append(str_issue)
        flag_valid = False
    # 1.2 if all columns are in right position
    for col_v, col in zip(list_col_forcing, col_df):
        if col_v != col:
            str_issue = f"Column {col} is not in the valid position"
            list_issues.append(str_issue)
            flag_valid = False

    # 2. valid timestamps:
    ind_df = df_forcing.index
    # 2.1 must be a temporal index
    if not isinstance(ind_df, pd.DatetimeIndex):
        str_issue = f"Index must be {pd.DatetimeIndex}"
        list_issues.append(str_issue)
        flag_valid = False
    # 2.2 no duplicates
    if ind_df.has_duplicates:
        ind_dup = ind_df[ind_df.duplicated()]
        str_issue = f"Timestamps have duplicates: {ind_dup}"
        list_issues.append(str_issue)
        flag_valid = False

    # 2.3 monotonically increasing
    if not ind_df.is_monotonic_increasing:
        str_issue = f"Timestamps must be monotonically increasing"
        list_issues.append(str_issue)
        flag_valid = False

    # 2.4 must have a valid `freq` attribute
    if hasattr(ind_df, "freq"):
        if ind_df.freq is None:
            str_issue = f"Temporal index must have a valid `freq`"
            list_issues.append(str_issue)
            flag_valid = False
    else:
        str_issue = f"Temporal index must have `freq` attribute"
        list_issues.append(str_issue)
        flag_valid = False

    # 3. valid physical ranges
    for var in col_df:
        if var not in ["iy", "id", "it", "imin", "isec"]:
            ser_var = df_forcing.loc[:, var].copy()
            res_check = check_range(ser_var, dict_rules_indiv)
            if not res_check[1]:
                str_issue = res_check[2]
                list_issues.append(str_issue)
                flag_valid = False
                if fix:
                    var_check = var.lower()
                    min_v = dict_rules_indiv[var_check]["param"]["min"]
                    max_v = dict_rules_indiv[var_check]["param"]["max"]
                    ser_var = ser_var.where(ser_var < max_v, max_v).copy()
                    ser_var = ser_var.where(ser_var > min_v, min_v).copy()
                    df_forcing_fix.loc[:, var] = ser_var.values

    if not flag_valid:
        str_issue = "\n".join(["Issues found in `df_forcing`:"] + list_issues)
        if not fix:
            logger_supy.error(str_issue)
            return list_issues
        else:
            logger_supy.info("detected issues have been fixed by clipping off outliers")
            return df_forcing_fix
    else:
        logger_supy.info("All checks for `df_forcing` passed!")
        if fix:
            return df_forcing


def check_state(df_state: pd.DataFrame, fix=True) -> List:
    logger_supy.info("SuPy is validating `df_state`...")
    # collect issues
    list_issues = []
    flag_valid = True

    # these variables dont have to be checked
    list_var_exclude = [
        "ts5mindata_ir",
    ]

    # variables defined in the rule json file:
    list_col_rule = set(dict_rules_indiv.keys()).difference(
        [x.lower() for x in list_col_forcing]
    )

    # check the following:
    # 0. mandatory variables in supy_driver
    set_diff = set_var_use.difference(set(list_col_rule).union(set(list_var_exclude)))
    if len(set_diff) > 0:
        str_issue = f"Mandatory parameters missing from rule file: {set_diff}"
        list_issues.append(str_issue)
        flag_valid = False

    # 1. correct columns
    col_df_state = df_state.columns.get_level_values("var")
    # 1.1 if all columns are present
    set_diff = set(list_col_rule).difference(col_df_state)
    if len(set_diff) > 0:
        str_issue = f"Mandatory columns missing from df_state: {set_diff}"
        list_issues.append(str_issue)
        flag_valid = False
    # 1.2 if all columns are included in the checking list
    set_diff = set(col_df_state).difference(list_col_rule)
    if len(set_diff) > 0:
        str_issue = f"Columns not included in checking list: {set_diff}"
        list_issues.append(str_issue)
        flag_valid = False

    # 2. check based on logic types
    list_to_check = set(col_df_state).intersection(list_col_rule)
    for var in list_to_check:
        # pack
        val = dict_rules_indiv[var]
        df_var = df_state[var]
        # 'NA' implies no checking required
        if val["logic"] != "NA":
            pass
        if val["logic"] == "range":
            for ind in df_var.index:
                ser_var = df_var.loc[ind].rename(var)
                res_check = check_range(ser_var, dict_rules_indiv)
                if not res_check[1]:
                    str_issue = res_check[2] + f" at index `{ind}`"
                    list_issues.append(str_issue)
                    flag_valid = False
        if val["logic"] == "method":
            for ind in df_var.index:
                ser_var = df_var.loc[ind].rename(var)
                res_check = check_method(ser_var, dict_rules_indiv)
                if not res_check[1]:
                    str_issue = res_check[2] + f" at index `{ind}`"
                    list_issues.append(str_issue)
                    flag_valid = False

    if not flag_valid:
        str_issue = "\n".join(["Issues found in `df_state`:"] + list_issues)
        logger_supy.error(str_issue)
        if not fix:
            return list_issues
        else:
            logger_supy.info(
                "Any issue detected will be fixed by filling dummy values: please check the results with caution!"
            )
            return upgrade_df_state(df_state)
    else:
        logger_supy.info("All checks for `df_state` passed!")


# flatten columns from MultiIndex to Index with compound notation
def flatten_col(df_state: pd.DataFrame):
    # original MultiIndex columsn
    col_mi = df_state.columns
    # flattened columns
    col_flat = col_mi.map(
        lambda s: (
            "_".join(s)
            .replace("_0", "")
            .replace("(", "")
            .replace(", ", "_")
            .replace(",)", "")
            .replace(")", "")
        )
    )
    # replace columns with flattened ones
    df_state_flat = df_state.set_axis(col_flat)
    return df_state_flat


# upgrade df_state from earlier versions of SuPy
def upgrade_df_state(df_state: pd.DataFrame) -> pd.DataFrame:
    df_state_deprecated = df_state.copy()
    # check if a df_state is before v2021a7
    if "sfr" in df_state.columns:
        logger_supy.info("A deprecated df_state is detected. Upgrading...")
        flag_upgrade = True
    else:
        logger_supy.info("The df_state is up to date. No upgrade required.")
        flag_upgrade = False

    # if so, upgrade it
    if flag_upgrade:
        from ._supy_module import init_supy

        # load base df_state
        path_SampleData = Path(trv_supy_module) / "sample_run"
        path_runcontrol = path_SampleData / "RunControl.nml"
        df_state_base = init_supy(path_runcontrol, force_reload=False)

        # rename columns
        dict_col_rename = {
            # these columns are renamed since v2021a7
            "sfr": "sfr_surf",
            "wetthresh": "wetthresh_surf",
            "soilstore_id": "soilstore_surf",
            "soilstorecap": "soilstorecap_surf",
            "state_id": "state_surf",
            "statelimit": "statelimit_surf",
            "qn1_av": "qn_av",
            "qn1_s_av": "qn_s_av",
        }
        for c_old, c_new in dict_col_rename.items():
            logger_supy.info(f"Column `{c_old}` is renamed to: `{c_new}`")
        df_state_upgrade = df_state_deprecated.rename(columns=dict_col_rename)

        # expand df_state_init to match df_state_init_test
        n_row, n_col = df_state_upgrade.shape
        df_state_init_base = df_state_base.loc[df_state_base.index.repeat(n_row)].copy()
        df_state_init_base.index = df_state_upgrade.index

        # add missing columns from sample data
        dict_col_add = {}
        for c in df_state_init_base.columns:
            if c in df_state_upgrade.columns:
                continue
            else:
                dict_col_add[c] = df_state_init_base[c]
                logger_supy.info(
                    f"A new column `{c}` is added with values: {dict_col_add[c].values}"
                )

        # merge processed dataframes
        df_state_init_add = pd.concat(dict_col_add, axis=1)
        df_state_upgrade = pd.concat([df_state_init_add, df_state_upgrade], axis=1)

        # add column levels
        df_state_upgrade.columns = df_state_upgrade.columns.set_names(
            ["var", "ind_dim"]
        )

        return df_state_upgrade
    else:
        return df_state_deprecated

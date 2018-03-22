"""
Absorption chillers
"""
from __future__ import division
import cea.config
import cea.globalvar
import cea.inputlocator
import pandas as pd
import numpy as np
from math import log
from cea.optimization.constants import *
from sympy import *
from cea.optimization.constants import *

__author__ = "Shanshan Hsieh"
__copyright__ = "Copyright 2015, Architecture and Building Systems - ETH Zurich"
__credits__ = ["Shanshan Hsieh"]
__license__ = "MIT"
__version__ = "0.1"
__maintainer__ = "Daren Thomas"
__email__ = "cea@arch.ethz.ch"
__status__ = "Production"


# technical model

def calc_chiller_abs_main(mdot_chw_kgpers, T_chw_sup_K, T_chw_re_K, T_hw_in_C, Qc_nom_W, locator, gv):
    """
    Assumptions: constant flow rate at the secondary sides (chilled water, cooling water, hot water)

    :type mdot_chw_kgpers : float
    :param mdot_chw_kgpers: plant supply mass flow rate to the district cooling network
    :type T_chw_sup_K : float
    :param T_chw_sup_K: plant supply temperature to DCN
    :type T_chw_re_K : float
    :param T_chw_re_K: plant return temperature from DCN
    :param gV: globalvar.py

    :rtype wdot : float
    :returns wdot: chiller electric power requirement
    :rtype qhotdot : float
    :returns qhotdot: condenser heat rejection

    ..[D.J. Swider, 2003] D.J. Swider (2003). A comparison of empirically based steady-state models for
    vapor-compression liquid chillers. Applied Thermal Engineering.

    """

    mcp_chw_WperK = mdot_chw_kgpers * gv.Cpw * 1000  # TODO: replace gv.Cpw
    q_chw_W = mcp_chw_WperK * (T_chw_re_K - T_chw_sup_K) if mdot_chw_kgpers != 0 else 0

    if q_chw_W == 0:
        wdot_W = 0
        q_cw_W = 0
        q_hw_W = 0
        T_hw_out_C = 0
    else:
        # solve operating conditions at given demand
        chiller_prop = read_chiller_properties_db(
            locator.get_supply_systems(gv.config.region))  # FIXME: choose chiller by size
        operating_conditions = calc_operating_conditions(T_chw_re_K, T_chw_sup_K, q_chw_W, T_hw_in_C, chiller_prop, gv)
        COP = 0.87
        wdot_W = operating_conditions['q_chw_W'] / COP  # FIXME: enter manufacturer data
        q_cw_W = operating_conditions['q_cw_W']  # to W
        q_hw_W = operating_conditions['q_hw_W']  # to W
        T_hw_out_C = operating_conditions['T_hw_out_C']

    chiller_operation = {'wdot_W': wdot_W, 'q_cw_W': q_cw_W, 'q_hw_W': q_hw_W, 'T_hw_out_C': T_hw_out_C}

    return chiller_operation


def calc_operating_conditions(T_chw_re_K, T_chw_sup_K, q_chw_W, T_hw_in_C, chiller_prop, gv):
    # external water circuits (e: chilled water, ac: cooling water, d: hot water)
    T_cw_in_C = 12  # condenser water inlet temperature # TODO: okay for now, but ideally, it should be connected to groud water temperature
    T_chw_in_C = T_chw_re_K - 273.0  # inlet to the evaporator
    T_chw_out_C = T_chw_sup_K - 273.0
    m_chw_kgpers = 0.722  # TODO: read from system database
    m_hw_kgpers = 0.333  # TODO: read from system database
    mcp_cw_WperK = m_chw_kgpers * gv.Cpw * 1000
    mcp_hw_WperK = m_hw_kgpers * gv.Cpw * 1000

    # technology specs # FIXME: read from system database
    # t = [np.nan, 0.42, 0.9, 0.53, -2.5, 0.94, -0.4]
    # u = [np.nan, -2.5, 1.8, -2.1, 1.5, -2.3, 1.6]

    # variables to solve
    T_hw_out_C, T_cw_out_C, q_hw_W = symbols('T_hw_out_C T_cw_out_C q_hw_W')

    # characteristic temperature differences
    T_hw_mean_C = (T_hw_in_C + T_hw_out_C) / 2
    T_cw_mean_C = (T_cw_in_C + T_cw_out_C) / 2
    T_chw_mean_C = (T_chw_in_C + T_chw_out_C) / 2
    ddt_e = T_hw_mean_C + chiller_prop['u1'] * T_cw_mean_C + chiller_prop['u2'] * T_chw_mean_C
    ddt_d = T_hw_mean_C + chiller_prop['u3'] * T_cw_mean_C + chiller_prop['u4'] * T_chw_mean_C

    # systems of equations
    eq_e = chiller_prop['t1'] * ddt_e + chiller_prop['t2'] - q_chw_W
    eq_d = chiller_prop['t3'] * ddt_d + chiller_prop['t4'] - q_hw_W
    eq_bal_d = (T_hw_in_C - T_hw_out_C) - q_hw_W / mcp_hw_WperK

    # solve the system of equation with sympy
    eq_sys = [eq_e, eq_d, eq_bal_d]
    unknown_variables = (T_hw_out_C, T_cw_out_C, q_hw_W)
    (T_hw_out_C, T_cw_out_C, q_hw_W) = tuple(*linsolve(eq_sys, unknown_variables))

    # calculate results
    q_cw_kW = q_hw_W + q_chw_W
    T_hw_out_C = T_hw_in_C - q_hw_W / mcp_hw_WperK
    T_cw_out_C = T_cw_in_C + q_cw_kW / mcp_cw_WperK

    return {'T_hw_out_C': T_hw_out_C, 'T_cw_out_C': T_cw_out_C, 'q_chw_W': q_chw_W, 'q_hw_W': q_hw_W,
            'q_cw_W': q_cw_kW}


def read_chiller_properties_db(database_path):
    data = pd.read_excel(database_path, sheetname="Abs_chiller")
    type_abs_chiller = 'ACH1'  # FIXME: choose according to size
    chiller_properties = data[data['code'] == type_abs_chiller].reset_index().T.to_dict()[0]
    return chiller_properties


# Investment costs

def calc_Cinv_chiller_abs(qcold_W, gv, locator, technology=0):
    """
    Annualized investment costs for the vapor compressor chiller

    :type qcold_W : float
    :param qcold_W: peak cooling demand in [W]
    :param gV: globalvar.py

    :returns InvCa: annualized chiller investment cost in CHF/a
    :rtype InvCa: float

    """
    if qcold_W > 0:
        cost_data = pd.read_excel(locator.get_supply_systems(gv.config.region), sheetname="Abs_chiller")
        technology_code = list(set(cost_data['code']))
        cost_data[cost_data['code'] == technology_code[technology]]
        # if the Q_design is below the lowest capacity available for the technology, then it is replaced by the least
        # capacity for the corresponding technology from the database
        if qcold_W < cost_data['cap_min'][0]:
            qcold_W = cost_data['cap_min'][0]
        cost_data = cost_data[
            (cost_data['cap_min'] <= qcold_W) & (cost_data['cap_max'] > qcold_W)]

        Inv_a = cost_data.iloc[0]['a']
        Inv_b = cost_data.iloc[0]['b']
        Inv_c = cost_data.iloc[0]['c']
        Inv_d = cost_data.iloc[0]['d']
        Inv_e = cost_data.iloc[0]['e']
        Inv_IR = (cost_data.iloc[0]['IR_%']) / 100
        Inv_LT = cost_data.iloc[0]['LT_yr']
        Inv_OM = cost_data.iloc[0]['O&M_%'] / 100

        InvC = Inv_a + Inv_b * (qcold_W) ** Inv_c + (Inv_d + Inv_e * qcold_W) * log(qcold_W)
        Capex_a = InvC * (Inv_IR) * (1 + Inv_IR) ** Inv_LT / ((1 + Inv_IR) ** Inv_LT - 1)
        Opex_fixed = Capex_a * Inv_OM
    else:
        Capex_a = 0
        Opex_fixed = 0

    return Capex_a, Opex_fixed


def main(config):
    """
    run the whole preprocessing routine
    """
    gv = cea.globalvar.GlobalVariables()
    locator = cea.inputlocator.InputLocator(scenario=config.scenario)
    mdot_chw_kgpers = 0.806
    T_chw_sup_K = 7 + 273.0
    T_chw_re_K = 10.9 + 273.0
    T_hw_in_C = 75
    building_name = 'B01'
    Qc_nom_W = 10000
    SC_data = pd.read_csv(locator.SC_results(building_name=building_name),
                          usecols=["T_SC_sup_C", "T_SC_re_C", "mcp_SC_kWperC", "Q_SC_gen_kWh"])
    calc_chiller_abs_main(mdot_chw_kgpers, T_chw_sup_K, T_chw_re_K, T_hw_in_C, Qc_nom_W, locator, gv)

    print 'test_decentralized_buildings_cooling() succeeded'


if __name__ == '__main__':
    main(cea.config.Configuration())

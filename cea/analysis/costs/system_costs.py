"""
costs according to supply systems
"""
from __future__ import division

import numpy as np
import pandas as pd
from geopandas import GeoDataFrame as gpdf

import cea.config
import cea.inputlocator
from cea.analysis.costs.equations import calc_capex_annualized, calc_opex_annualized

__author__ = "Jimeno A. Fonseca"
__copyright__ = "Copyright 2020, Architecture and Building Systems - ETH Zurich"
__credits__ = ["Jimeno A. Fonseca", " Emanuel Riegelbauer"]
__license__ = "MIT"
__version__ = "0.1"
__maintainer__ = "Daren Thomas"
__email__ = "cea@arch.ethz.ch"
__status__ = "Production"


def costs_main(locator, config):
    # get local variables
    capital = config.costs.capital
    operational = config.costs.operational

    # get demand
    demand = pd.read_csv(locator.get_total_demand())

    # get the databases for each main system
    cooling_db, hot_water_db, electricity_db, heating_db = get_databases(demand, locator)

    # COSTS DUE TO HEATING SERIVICES (EXCEPT HOTWATER)
    heating_final_services = ['OIL_hs', 'NG_hs', 'WOOD_hs', 'COAL_hs', 'GRID_hs', 'DH_hs']
    costs_heating_services_dict = calc_costs_per_energy_service(heating_db, heating_final_services)

    # COSTS DUE TO HOT WATER SERVICES
    hot_water_final_services = ['OIL_ww', 'NG_ww', 'WOOD_ww', 'COAL_ww', 'GRID_ww', 'DH_ww']
    costs_hot_water_services_dict = calc_costs_per_energy_service(hot_water_db, hot_water_final_services)

    # COSTS DUE TO COOLING SERVICES
    cooling_final_services = ['GRID_cs', 'GRID_cdata', 'GRID_cre', 'DC_cs']
    costs_cooling_services_dict = calc_costs_per_energy_service(cooling_db, cooling_final_services)

    # COSTS DUE TO ELECTRICITY SERVICES
    electricity_final_services = ['GRID_pro', 'GRID_l', 'GRID_aux', 'GRID_v', 'GRID_a', 'GRID_data']
    costs_electricity_services_dict = calc_costs_per_energy_service(electricity_db, electricity_final_services)

    # COMBINE INTO ONE DICT
    result = dict(costs_heating_services_dict.items() + costs_hot_water_services_dict.items() +
                  costs_cooling_services_dict.items() + costs_electricity_services_dict.items())

    # sum up for all fields
    #create a dict to map from the convention of fields to the final variables
    mapping_dict = {'_capex_total_USD': 'Capex_total_sys_USD',
                   '_opex_fixed_USD': 'Opex_fixed_sys_USD',
                   '_opex_var_USD': 'Opex_var_sys_USD',
                   '_opex_USD': 'Opex_sys_USD',
                   # all system annualized
                   '_capex_a_USD': 'Capex_a_sys_USD',
                   '_opex_a_var_USD': 'Opex_a_var_sys_USD',
                   '_opex_a_fixed_USD': 'Opex_a_fixed_sys_USD',
                   '_opex_a_USD': 'Opex_a_sys_USD',
                   '_TAC_USD': 'TAC_sys_USD',
                   # disconnected system
                   '_capex_total_disconnected_USD': 'Capex_total_sys_disconnected_USD',
                   '_opex_disconnected_USD': 'Opex_sys_disconnected_USD',
                   '_capex_a_disconnected_USD': 'Capex_a_sys_disconnected_USD',
                   '_opex_a_disconnected_USD': 'Opex_a_sys_disconnected_USD',
                   # connected system
                   '_capex_total_connected_USD': 'Capex_total_sys_connected_USD',
                   '_opex_connected_USD': 'Opex_sys_connected_USD',
                   '_capex_a_connected_USD': 'Capex_a_sys_connected_USD',
                   '_opex_a_connected_USD':'Opex_a_sys_connected_USD'
                   }
    # initialize the names of the variables in the result to zero
    n_buildings = demand.shape[0]
    for _, value in mapping_dict.items():
        result[value] = np.zeros(n_buildings)

    # loop inside the results and sum the results
    for field in result.keys():
        for key, value in mapping_dict.items():
            if key in field:
                result[value] += result[field]

    # add name and create dataframe
    result.update({'Name': demand.Name.values})
    result_out = pd.DataFrame(result)

    # save dataframe
    result_out.to_csv(locator.get_costs_operation_file(), index=False, float_format='%.2f')


def calc_costs_per_energy_service(database, heating_services):
    result = {}
    for service in heating_services:
        # TOTALS
        result[service + '_capex_total_USD'] = (database[service + '0_kW'].values *
                                                database['efficiency'].values *  # because it is based on the end use
                                                database['CAPEX_USD2015kW'].values)

        result[service + '_opex_fixed_USD'] = (result[service + '_capex_total_USD'] * database['O&M_%'].values / 100)

        result[service + '_opex_var_USD'] = database[service + '_MWhyr'].values * database['Opex_var_buy_USD2015kWh'].values * 1000

        result[service + '_opex_USD'] = result[service + '_opex_fixed_USD'] + result[service + '_opex_var_USD']

        # ANNUALIZED
        result[service + '_capex_a_USD'] = np.vectorize(calc_capex_annualized)(result[service + '_capex_total_USD'],
                                                                               database['IR_%'],
                                                                               database['LT_yr'])

        result[service + '_opex_a_fixed_USD'] = np.vectorize(calc_opex_annualized)(result[service + '_opex_fixed_USD'],
                                                                                   database['IR_%'],
                                                                                   database['LT_yr'])

        result[service + '_opex_a_var_USD'] = np.vectorize(calc_opex_annualized)(result[service + '_opex_var_USD'],
                                                                                 database['IR_%'],
                                                                                 database['LT_yr'])

        result[service + '_opex_a_USD'] = np.vectorize(calc_opex_annualized)(result[service + '_opex_USD'],
                                                                             database['IR_%'],
                                                                             database['LT_yr'])

        result[service + '_TAC_USD'] = result[service + '_opex_a_USD'] + result[service + '_capex_a_USD']

        # GET CONNECTED AND DISCONNECTED
        for field in ['_capex_total_USD', '_capex_a_USD', '_opex_USD', '_opex_a_USD']:
            field_connected = field.split("_USD")[0] + "_connected_USD"
            field_disconnected = field.split("_USD")[0] + "_disconnected_USD"
            result[service + field_connected], \
            result[service + field_disconnected] = np.vectorize(calc_connected_disconnected)(result[service + field],
                                                                                             database['scale'])
    return result


def calc_connected_disconnected(value, flag_scale):
    if flag_scale == "BUILDING":
        connected = 0.0
        disconnected = value
    elif flag_scale == "DISTRICT":
        connected = value
        disconnected = 0.0
    elif flag_scale == "CITY":
        connected = value
        disconnected = 0.0
    elif flag_scale == "NONE":
        if value == 0.0:
            connected = 0.0
            disconnected = 0.0
        else:
            raise ValueError("the scale is NONE but somehow there is a cost here?"
                             " the inputs of SUPPLY database may be wrong")
    return connected, disconnected


def get_databases(demand, locator):
    supply_systems = gpdf.from_file(locator.get_building_supply()).drop('geometry', axis=1)
    data_all_in_one_systems = pd.read_excel(locator.get_database_supply_assemblies(), sheet_name=None)
    factors_heating = data_all_in_one_systems['HEATING']
    factors_dhw = data_all_in_one_systems['HOT_WATER']
    factors_cooling = data_all_in_one_systems['COOLING']
    factors_electricity = data_all_in_one_systems['ELECTRICITY']
    factors_resources = pd.read_excel(locator.get_database_feedstocks(), sheet_name=None)
    # get the mean of all values for this
    factors_resources_simple = [(name, values['Opex_var_buy_USD2015kWh'].mean()) for name, values in
                                factors_resources.items()]
    factors_resources_simple = pd.DataFrame(factors_resources_simple,
                                            columns=['code', 'Opex_var_buy_USD2015kWh']).append(
        # append NONE choice with zero values
        {'code': 'NONE'}, ignore_index=True).fillna(0)
    # local variables
    # calculate the total operational non-renewable primary energy demand and CO2 emissions
    ## create data frame for each type of end use energy containing the type of supply system use, the final energy
    ## demand and the primary energy and emissions factors for each corresponding type of supply system
    heating_costs = factors_heating.merge(factors_resources_simple, left_on='feedstock', right_on='code')[
        ['code_x', 'feedstock', 'scale', 'efficiency', 'Opex_var_buy_USD2015kWh', 'CAPEX_USD2015kW', 'LT_yr', 'O&M_%',
         'IR_%']]
    cooling_costs = factors_cooling.merge(factors_resources_simple, left_on='feedstock', right_on='code')[
        ['code_x', 'feedstock', 'scale', 'efficiency', 'Opex_var_buy_USD2015kWh', 'CAPEX_USD2015kW', 'LT_yr', 'O&M_%',
         'IR_%']]
    dhw_costs = factors_dhw.merge(factors_resources_simple, left_on='feedstock', right_on='code')[
        ['code_x', 'feedstock', 'scale', 'efficiency', 'Opex_var_buy_USD2015kWh', 'CAPEX_USD2015kW', 'LT_yr', 'O&M_%',
         'IR_%']]
    electricity_costs = factors_electricity.merge(factors_resources_simple, left_on='feedstock', right_on='code')[
        ['code_x', 'feedstock', 'scale', 'efficiency', 'Opex_var_buy_USD2015kWh', 'CAPEX_USD2015kW', 'LT_yr', 'O&M_%',
         'IR_%']]
    heating = supply_systems.merge(demand, on='Name').merge(heating_costs, left_on='type_hs', right_on='code_x')
    dhw = supply_systems.merge(demand, on='Name').merge(dhw_costs, left_on='type_dhw', right_on='code_x')
    cooling = supply_systems.merge(demand, on='Name').merge(cooling_costs, left_on='type_cs', right_on='code_x')
    electricity = supply_systems.merge(demand, on='Name').merge(electricity_costs, left_on='type_el', right_on='code_x')
    return cooling, dhw, electricity, heating


def main(config):
    locator = cea.inputlocator.InputLocator(scenario=config.scenario)

    print('Running system-costs with scenario = %s' % config.scenario)

    costs_main(locator=locator, config=config)


if __name__ == '__main__':
    main(cea.config.Configuration())

# -*- coding: utf-8 -*-
import dash
import dash_html_components as html
import dash_core_components as dcc
from dash.dependencies import Input, Output, State
from app_common import app
import db_common as dbc


layout = html.Div([
    html.H2(u'创建子账户'),

    html.Div(
        dcc.Input(
            id='account-name',
            type='text',
            placeholder=u'子账户名'
        ),
    ),

    html.Button('Ok', id='button-ok', n_clicks=0),
    html.Button('Cancel', id='button-cancel', n_clicks=0),

    html.Div(id='output'),
])


def show():
    return layout


@app.callback(
    Output('output', 'children'),
    [Input('button-ok', 'n_clicks')],
    [State('account-name', 'value')]
)
def create_subaccount(n_clicks, value):
    if dbc.table_exist(value):
        return f'{value} already exists'
    else:
        dbc.create_sub_account_table(value)
        return f'create {value} successfully'


@app.callback(Output('url', 'pathname'),
              [Input('button-cancel', 'n_clicks')])
def chick_cancel(n_clicks):
    return '/'
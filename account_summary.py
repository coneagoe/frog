# -*- coding: utf-8 -*-
import dash
import dash_html_components as html
import dash_core_components as dcc
from dash.dependencies import Input, Output, State
from app_common import app


layout = html.Div([
    html.H2(u'总资产账户'),
    html.Button(u'创建子账户', id='button-new-account', n_clicks=0)
])


def show():
    return layout


@app.callback(Output('url', 'pathname'),
              [Input('button-new-account', 'n_clicks')])
def chick_new_account(n_clicks):
    return '/create_account'
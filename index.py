# -*- coding: utf-8 -*-
import dash_html_components as html
import dash_core_components as dcc
from dash.dependencies import Input, Output
from app_common import app
import account_summary
import create_account
import db_common as dbc

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])


@app.callback(Output('page-content', 'children'),
              [Input('url', 'pathname')])
def display_page(pathname):
    if pathname == '/':
        return account_summary.show()
    elif pathname == '/create_account':
        return create_account.show()
    else:
        return '404'


if __name__ == '__main__':
    dbc.init()
    app.run_server(debug=True)
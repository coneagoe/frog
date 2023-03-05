import logging
from os import walk
from datetime import date
import plotly.express as px
from dash import Dash, html, dcc
from dash.dependencies import Input, Output
import conf
from fund import *


df_asset, df_profit, df_profit_rate = (None, None, None)

conf.config = conf.parse_config()


def get_available_date_range() -> (str, str):
    filenames = next(walk(get_fund_position_path()), (None, None, []))[2]
    if len(filenames) > 0:
        start_date = filenames[0].rstrip('.csv')
        end_date = filenames[-1].rstrip('.csv')
        return start_date, end_date
    else:
        logging.info("No history fund position data")
        exit()


start_date, end_date = get_available_date_range()

app = Dash(__name__)
app.layout = html.Div(children=[
    html.H1(children=u'基金历史账户'),

    html.Div([
        dcc.DatePickerRange(
            id='date-range-picker',
            min_date_allowed=start_date,
            max_date_allowed=end_date,
            initial_visible_month=end_date
        )
    ]),

    dcc.Graph(id='asset-graph')
])


@app.callback(
    Output('asset-graph', 'figure'),
    Input('date-range-picker', 'start_date'),
    Input('date-range-picker', 'end_date'))
def update_asset_graph(start_date, end_date):
    # string_prefix = 'You have selected: '
    # if start_date is not None:
    #     start_date_object = date.fromisoformat(start_date)
    #     start_date_string = start_date_object.strftime('%B %d, %Y')
    #     string_prefix = string_prefix + 'Start Date: ' + start_date_string + ' | '

    # if end_date is not None:
    #     end_date_object = date.fromisoformat(end_date)
    #     end_date_string = end_date_object.strftime('%B %d, %Y')
    #     string_prefix = string_prefix + 'End Date: ' + end_date_string

    if start_date and end_date:
        df_asset, df_profit, df_profit_rate = load_history_position(start_date, end_date)

        fig = px.line(df_asset, x="date", y="price", title='Life expectancy in Canada')

        fig.update_layout(margin={'l': 40, 'b': 40, 't': 10, 'r': 0}, hovermode='closest')

        # fig.update_xaxes(title=xaxis_column_name,
        #                  type='linear' if xaxis_type == 'Linear' else 'log')

        # fig.update_yaxes(title=yaxis_column_name,
        #                  type='linear' if yaxis_type == 'Linear' else 'log')

        return fig
        # return df_asset


if __name__ == '__main__':
    app.run_server(debug=True)

    # print(df_asset)
    # print(df_profit)
    # print(df_profit_rate)

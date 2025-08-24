import dash
from dash import html, dcc, Input, Output, State, ctx, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import datetime
import sys
import os
import re
from typing import List, Dict
import glob
import gspread
from google.oauth2.service_account import Credentials
from googleads import ad_manager
import shutil
import base64
import time
import uuid

# Add the parent directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# Import logging utility
from logging_utils import logger

# Import email utility
from email_utils import get_default_email_with_fallback

# Configure assets folder path
assets_folder = os.path.join(parent_dir, 'assets')

# Now import the modules after adding parent directory to path
from create_order import create_order
from single_line import single_line
from single_line import LocationNotFoundError
from config import CREATIVES_FOLDER
from DSD.Dsd_Download import Dsd_Download
from dsd_read import load_dsd
from fetch_expresso_details import fetch_full_expresso_details
from authenticate_google_cloud import get_ads_client, setup_authentication

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY], assets_folder=assets_folder)
server = app.server

# Dropdown Options
dropdown_style = {"className": "mb-2 form-field"}
industry_options = [{'label': i, 'value': i} for i in [
    "Industry - FMCG", "Industry - Auto", "Industry - B2B", "Industry - BFSI",
    "Industry - Education", "Industry - Ecommerce", "Industry - Entertainment",
    "Industry - Family & parenting", "Industry - Food & drinks", "Industry - Gaming",
    "Industry - Health & fitness", "Industry - Govt.", "Industry - Home & living",
    "Industry - In-house promotion", "Industry - Jobs & careers", "Industry - Real estate",
    "Industry - Telecom", "Retail","Industry - Travel","Industry - Luxury products","Industry - Tech"


]]
site_options = [{'label': s, 'value': s} for s in ["TOI", "ETIMES", "ET", "ALL_Languages", "IAG", "ITBANGLA", "MS", "MT", "NBT", "TLG", "TML", "VK"]]
platform_options = [{'label': p, 'value': p} for p in ["Web", "Mweb", "AMP", "IOS", "AOS"]]
fcap_options = [{'label': str(i), 'value': str(i)} for i in range(6)]
currency_options = [{'label': c, 'value': c} for c in ["INR", "USD", "CAD", "AED","GBP", "EUR", "SGD"]]

# Get auto-detected email
try:
    auto_detected_email = get_default_email_with_fallback()
    print(f"🔍 Auto-detected email for Dash app: {auto_detected_email}")
except Exception as e:
    print(f"⚠️ Error detecting email: {e}")
    auto_detected_email = 'anurag.mishra@timesinternet.in'

# Add email options with auto-detected email at the top
predefined_emails = [
    'Nitesh.pandey1@timesinternet.in',
    'Nikhil.yadav@timesinternet.in',
    'Anurag.mishra1@timesinternet.in',
    'Amit.jha@timesinternet.in',
    'Sneha.som@timesinternet.in',
    'Abhijeet.raushan@timesinternet.in',
    'Shamayla.khan@timesinternet.in',
    'Sudhanshu@timesinternet.in',
    'Deepak.khundiya@timesinternet.in'
]

# Create email options list
email_options = [{'label': email, 'value': email} for email in predefined_emails]

# Add auto-detected email first if it's not in predefined list
#if auto_detected_email not in predefined_emails:
#    email_options.append({
#        'label': f"{auto_detected_email}", 
#        'value': auto_detected_email
#    })
#
## Add all predefined emails
#for email in predefined_emails:
#    email_options.append({'label': email, 'value': email})

# Store submission data
submissions = []

# SHEET_ID = "1cj4vEb1aJ9Uqrd7BwPwdWfcnT1aOZQ151OWJQn6mx6o"
SHEET_ID = "1LvTZELsn6m5NMkvkiEz6NjH01ZxUzHfwRYzSEK3Sphw"
RANGE = "Sheet1"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
credentials = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
sheets_client = gspread.authorize(credentials)

# App Layout
app.layout = dbc.Container([
    dbc.Row([
        # Left side: Welcome/info
        dbc.Col([
            html.Div([
                html.Img(
                    src="/assets/banner.jpg",
                    style={
                        "maxWidth": "100%",
                        "maxHeight": "100vh",
                        "width": "auto",
                        "height": "auto",
                        "objectFit": "contain",
                        "borderRadius": "24px",
                        "display": "block",
                        "margin": "0"
                    },
                    alt="Configura Banner (image not found)"
                )
            ], style={
                "borderTopLeftRadius": "24px",
                "borderBottomLeftRadius": "24px",
                "padding": "0",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.1)",
                "color": "#fff",
                "height": "100vh",
                "width": "auto",
                "position": "relative",
                "display": "flex",
                "alignItems": "flex-start",
                "justifyContent": "flex-start"
            })
        ], width=3),
        # Right side: Form (centered vertically and horizontally)
        dbc.Col([
            html.H3("Create the GAM Line", style={"textAlign": "center", "marginBottom": "24px"}),
            html.Div([
                # Static Alert for error messages in corner
                dbc.Alert(
                    id='form-error',
                    color='danger',
                    is_open=False,
                    style={
                        "position": "fixed",
                        "top": "20px",
                        "right": "20px",
                        "zIndex": "1000",
                        "width": "300px",
                        "boxShadow": "0 4px 8px rgba(0,0,0,0.1)"
                    }
                ),

                # First row: Order type dropdown and Order ID
                dbc.Row([
                    dbc.Col(
                        dcc.Dropdown(
                            id='order_option',
                            options=[
                                {'label': 'New Order', 'value': 'new'},
                                {'label': 'Order Already Created', 'value': 'existing'}
                            ],
                            value='new',
                            placeholder="Select Order Type",
                            className="form-field"
                        ),
                        width=6
                    ),
                    dbc.Col(
                            dbc.Input(
                                id='order_id',
                                placeholder="Enter Order ID",
                                type="text",
                                className="form-field"
                            ),
                        width=6,
                            id='order-id-col',
                            style={"display": "none"}
                    ),
                ], className="mb-3"),
                
                # Second row: Email dropdown and Expresso ID (always visible)
                dbc.Row([
                    dbc.Col(
                        dcc.Dropdown(
                            id='email',
                            options=email_options,
                            value=predefined_emails[0],
                            placeholder="Select Email",
                            className="form-field"
                        ),
                        width=6
                    ),
                    dbc.Col(
                        dbc.Input(
                            id='expresso',
                            placeholder="Enter Expresso ID",
                            type="number",
                            className="form-field"
                        ),
                        width=6
                    ),
                ], className="mb-3"),

                # Rest of the form fields
            html.Div([
                # Two fields per row
                dbc.Row([
                    dbc.Col(dcc.Dropdown(id='label', options=industry_options, placeholder="Select Industry Label", className="mb-2 form-field"), width=6),
                    dbc.Col(dbc.Input(id='line_name', placeholder="Enter Line item from Expresso", type="text", className="mb-2 form-field"), width=6),
                ]),
                dbc.Row([
                    dbc.Col(dcc.Dropdown(id='site', options=site_options, multi=True, placeholder="Select Pub Sites", className="mb-2 form-field"), width=6),
                    dbc.Col(dcc.Dropdown(id='platform', options=platform_options, multi=True, placeholder="Select Platforms", className="mb-2 form-field"), width=6),
                ]),
                dbc.Row([
                    dbc.Col([
                        dbc.Input(
                            id='geo-input',
                            type='text',
                            placeholder='Enter geos, separated by commas',
                            className="mb-2 form-field"
                        ),
                    ], width=6),
                    dbc.Col(dcc.Dropdown(id='fcap', options=fcap_options, placeholder="Enter FCAP Value", className="mb-2 form-field"), width=6),
                ]),
                dbc.Row([
                    dbc.Col(dcc.Dropdown(id='currency', options=currency_options, placeholder="Select Currency", className="mb-2 form-field"), width=6),
                    dbc.Col(dbc.Input(id='impressions', placeholder="Enter Goal (CPM)", type="number", className="mb-2 form-field"), width=6),
                ]),
                dbc.Row([
                    dbc.Col(dbc.Input(id='destination_url', placeholder="Enter Landing Page URL", className="mb-2 form-field"), width=6),
                    dbc.Col(dbc.Input(id='impression_tracker', placeholder="Enter Impression Tracker", className="mb-2 form-field"), width=6),
                ]),
                dbc.Row([
                    dbc.Col(dbc.Input(id='tracking_tag', placeholder="Enter Script code", className="mb-2 form-field"), width=6),
                    dbc.Col(dbc.Input(id='banner_video', placeholder="Enter In-banner Video URL", className="mb-2 form-field"), width=6),
                ]),
            ]),
            ], style={"marginBottom": "20px"}),
            # Label for upload creative
            html.P("Use name tag for tracker and Tag file", style={"marginBottom": "8px", "fontWeight": "500", "color": "#495057"}),
            # Upload Creative Button moved here
            dcc.Upload(
                id='upload-creative',
                children=html.Div([
                    'Upload Creative',
                    html.I(className="bi bi-upload ms-2")
                ]),
                style={
                    'width': '100%', 'height': '50px', 'lineHeight': '50px',
                    'borderWidth': '1px', 'borderStyle': 'dashed', 'borderRadius': '8px',
                    'textAlign': 'center', 'marginBottom': '16px', 'background': '#f8f9fa'
                },
                multiple=True
            ),
            html.Div(id='upload-status', style={"marginBottom": "16px"}),
            dcc.Store(id='uploaded-files-store', data=[]),
            dbc.Row([
                dbc.Col([
                    dbc.Button("Preview", id="preview-btn", color="info", className="me-2"),
                    dbc.Button("Submit", id="submit-btn", color="success", className="me-2"),
                    dbc.Button("Clear", id="clear-btn", color="danger"),
                ], className="my-3 text-center")
            ]),
            html.Hr(),
            html.H4("Submissions", className="my-3"),
            dash_table.DataTable(
                id='submission-table',
                columns=[
                    {'name': 'Sr. No.', 'id': 'sr'},
                    {'name': 'User Name', 'id': 'user'},
                    {'name': 'Expresso ID', 'id': 'expresso'},
                    {'name': 'GAM Order ID', 'id': 'gam_id'},
                    {'name': 'Date and Time', 'id': 'timestamp'}
                ],
                data=[],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left'},
            ),
            dbc.Modal([
                dbc.ModalHeader("Preview Submission"),
                dbc.ModalBody(id='preview-content'),
                dbc.ModalFooter(
                    dbc.Button("Close", id="close-preview", className="ms-auto")
                )
            ], id="preview-modal", is_open=False),
        ], style={"background": "#f5f5f5", "borderRadius": "13px", "padding": "24px 12px", "boxShadow": "0 2px 8px rgba(0,0,0,0.1)", "width": "90%", "color": "#222", "paddingRight": "32px"})
    ], className="mx-auto h-100 d-flex align-items-center", style={"paddingLeft": "0", "minHeight": "100vh", "margin": "0", "gap": "0"})
], fluid=True, style={"minHeight": "100vh", "paddingLeft": "0", "paddingRight": "0", "padding": "0", "margin": "0"})

# --- Callbacks ---

# Preview Callback
@app.callback(
    Output('preview-modal', 'is_open'),
    Output('preview-content', 'children'),
    Input('preview-btn', 'n_clicks'),
    Input('close-preview', 'n_clicks'),
    State('email', 'value'),
    State('expresso', 'value'),
    State('label', 'value'),
    State('line_name', 'value'),
    State('site', 'value'),
    State('platform', 'value'),
    State('geo-input', 'value'),
    State('fcap', 'value'),
    State('currency', 'value'),
    State('impressions', 'value'),
    State('destination_url', 'value'),
    State('impression_tracker', 'value'),
    State('tracking_tag', 'value'),
    State('banner_video', 'value'),
    State('order_option', 'value'),
    prevent_initial_call=True
)
def toggle_preview(preview_click, close_click, email, expresso, label, line_name, site, platform,
                   geo_input, fcap, currency, impressions, destination_url, impression_tracker,
                   tracking_tag, banner_video, order_option):
    if ctx.triggered_id == "preview-btn":
        preview_text = html.Div([
            html.P(f"User: {email}"),
            html.P(f"Expresso ID: {expresso}"),
            html.P(f"Industry Label: {label}"),
            html.P(f"Line Name: {line_name}"),
            html.P(f"Site: {site}"),
            html.P(f"Platform: {platform}"),
            html.P(f"Geo: {', '.join(geo_input.split(',')) if geo_input else ''}"),
            html.P(f"FCAP: {fcap}"),
            html.P(f"Currency: {currency}"),
            html.P(f"Impressions: {impressions}"),
            html.P(f"Destination URL: {destination_url}"),
            html.P(f"Impression Tracker: {impression_tracker}"),
            html.P(f"Tracking Tag: {tracking_tag}"),
            html.P(f"In-Banner Video: {banner_video}"),
        ])
        return True, preview_text
    return False, ""

# Update callback to only handle order_id visibility
@app.callback(
    [Output('order-id-col', 'style')],
    Input('order_option', 'value')
)
def toggle_fields_visibility(order_option):
    if order_option == 'existing':
        return [{"display": "block"}]
    else:
        return [{"display": "none"}]

# Main callback - remove allow_duplicate and placeholder change
@app.callback(
    Output('submission-table', 'data'),
    Output('email', 'value'),
    Output('expresso', 'value'),
    Output('label', 'value'),
    Output('line_name', 'value'),
    Output('site', 'value'),
    Output('platform', 'value'),
    Output('fcap', 'value'),
    Output('currency', 'value'),
    Output('impressions', 'value'),
    Output('destination_url', 'value'),
    Output('impression_tracker', 'value'),
    Output('tracking_tag', 'value'),
    Output('banner_video', 'value'),
    Output('form-error', 'children'),
    Output('form-error', 'is_open'),
    Output('upload-status', 'children'),
    Output('uploaded-files-store', 'data'),
    Input('submit-btn', 'n_clicks'),
    Input('clear-btn', 'n_clicks'),
    Input('order_option', 'value'),
    Input('upload-creative', 'contents'),
    State('upload-creative', 'filename'),
    State('email', 'value'),
    State('order_id', 'value'),
    State('expresso', 'value'),
    State('label', 'value'),
    State('line_name', 'value'),
    State('site', 'value'),
    State('platform', 'value'),
    State('geo-input', 'value'),
    State('fcap', 'value'),
    State('currency', 'value'),
    State('impressions', 'value'),
    State('destination_url', 'value'),
    State('impression_tracker', 'value'),
    State('tracking_tag', 'value'),
    State('banner_video', 'value'),
    State('order_option', 'value'),
    State('uploaded-files-store', 'data'),
    prevent_initial_call=True
)
def handle_all_inputs(submit_n, clear_n, order_option_trigger, upload_contents, upload_filenames,
                     email, order_id, expresso, label, line_name, site, platform, geo_input, fcap, currency,
                     impressions, destination_url, impression_tracker, tracking_tag, banner_video, order_option, stored_files):
    
    if not ctx.triggered:
        return [dash.no_update] * 18

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Handle file upload
    if triggered_id == 'upload-creative':
        if upload_contents is not None and upload_filenames is not None:
            alerts = []
            stored_files = stored_files or []
            
            # Ensure upload_contents and upload_filenames are lists
            if not isinstance(upload_contents, list):
                upload_contents = [upload_contents]
                upload_filenames = [upload_filenames]

            os.makedirs(CREATIVES_FOLDER, exist_ok=True)

            for content, filename in zip(upload_contents, upload_filenames):
                content_type, content_string = content.split(',')
                decoded = base64.b64decode(content_string)
                save_path = os.path.join(CREATIVES_FOLDER, filename)
                with open(save_path, 'wb') as f:
                    f.write(decoded)
                
                if filename not in stored_files:
                    stored_files.append(filename)
            
            # Create alerts for all stored files
            for filename in stored_files:
                alerts.append(
                    dbc.Alert(
                        f"✓ {filename}",
                        color="success",
                        className="mb-1",
                        style={
                            "padding": "5px 10px",
                            "display": "inline-block",
                            "marginRight": "10px"
                        }
                    )
                )
            
            upload_status = html.Div(alerts, style={"marginBottom": "10px"})
            return [dash.no_update] * 16 + [upload_status, stored_files]

        return [dash.no_update] * 18

    # Clear button logic
    if triggered_id == 'clear-btn':
        try:
            # Clear creatives folder
            if os.path.exists(CREATIVES_FOLDER):
                for file_name in os.listdir(CREATIVES_FOLDER):
                    file_path = os.path.join(CREATIVES_FOLDER, file_name)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except Exception as e:
                        print(f"Error removing {file_path}: {e}")
            else:
                os.makedirs(CREATIVES_FOLDER, exist_ok=True)
            
            # Clear downloads folder
            downloads_folder = os.path.join(parent_dir, 'downloads')
            if os.path.exists(downloads_folder):
                for file_name in os.listdir(downloads_folder):
                    file_path = os.path.join(downloads_folder, file_name)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except Exception as e:
                        print(f"Error removing {file_path}: {e}")
            else:
                os.makedirs(downloads_folder, exist_ok=True)
            
            # Clear other folders and files as before...
            
            return ([], None, None, None, None, [], [], None, None, None, None, None, None, None, None, False, None, [])
        except Exception as e:
            print(f"Error in clear operation: {e}")
            return [dash.no_update] * 14 + [f"Error clearing data: {str(e)}", True, None, dash.no_update]

    # Order option logic
    if triggered_id == 'order_option':
        return [dash.no_update] * 18

    # Submission logic
    if triggered_id == 'submit-btn':
        # Generate session ID for this submission
        session_id = str(uuid.uuid4())
        
        try:
            # Validate expresso ID
            if not expresso:
                return [dash.no_update] * 14 + ["Enter Expresso ID", True, None, dash.no_update]
            try:
                expresso_number = int(expresso)
            except (ValueError, TypeError):
                return [dash.no_update] * 14 + ["Expresso ID must be a numerical value", True, None, dash.no_update]

            # Validate required fields
            if order_option == 'existing' and not order_id:
                return [dash.no_update] * 14 + ["Enter Order ID", True, None, dash.no_update]
            if not line_name:
                return [dash.no_update] * 14 + ["Enter Line item from Expresso", True, None, dash.no_update]
            if not site:
                return [dash.no_update] * 14 + ["Select Pub Sites", True, None, dash.no_update]
            if not platform:
                return [dash.no_update] * 14 + ["Select Platforms", True, None, dash.no_update]
            if not geo_input:
                return [dash.no_update] * 14 + ["Enter geos, separated by commas", True, None, dash.no_update]
            if not fcap:
                return [dash.no_update] * 14 + ["Enter FCAP Value", True, None, dash.no_update]
            if not currency:
                return [dash.no_update] * 14 + ["Select Currency", True, None, dash.no_update]
            if not impressions:
                return [dash.no_update] * 14 + ["Enter Goal(Impression)", True, None, dash.no_update]

            # Process the submission
            # Clean and validate geo input
            geo_list = []
            if geo_input:
                if isinstance(geo_input, str):
                    geo_list = [g.strip() for g in geo_input.split(',') if g.strip()]
                elif isinstance(geo_input, list):
                    geo_list = [str(g).strip() for g in geo_input if str(g).strip()]
            
            if not geo_list:
                return [dash.no_update] * 14 + ["Enter valid geos, separated by commas", True, None, dash.no_update]

            line_item_data = {
                "email": email,
                "order_id": order_id if order_option == 'existing' else None,
                "expresso_id": expresso_number,
                "label": label or '',
                "line_name": line_name.strip() if line_name else '',
                "site": site,
                "platforms": platform,
                "geo": geo_list,  # Use the cleaned geo list
                "fcap": fcap or '0',
                "currency": (currency or 'INR').upper(),
                "impressions": float(impressions or 0),
                "destination_url": destination_url,
                "impression_tracker": impression_tracker or '',
                "tracking_tag": tracking_tag or '',
                "banner_video": banner_video or ''
            }

            print(f"Initial line_item_data::{line_item_data}")
            
            # Log user input data
            logger.log_user_input({
                'email': email,
                'order_option': order_option,
                'order_id': order_id,
                'expresso_id': expresso_number,
                'label': label,
                'line_name': line_name,
                'site': site,
                'platforms': platform,
                'geo': geo_list,
                'fcap': fcap,
                'currency': currency,
                'impressions': impressions,
                'destination_url': destination_url,
                'impression_tracker': impression_tracker,
                'tracking_tag': tracking_tag,
                'banner_video': banner_video,
                'uploaded_files': stored_files
            }, session_id)
            
            # Validate and clean data
            if not line_item_data['site']:
                return [dash.no_update] * 14 + ["Select Pub Sites", True, None, dash.no_update]
            if not line_item_data['platforms']:
                return [dash.no_update] * 14 + ["Select Platforms", True, None, dash.no_update]
            if not line_item_data['geo']:
                return [dash.no_update] * 14 + ["Enter geos, separated by commas", True, None, dash.no_update]
            if not line_item_data['line_name']:
                return [dash.no_update] * 14 + ["Enter Line item from Expresso", True, None, dash.no_update]
            
            # Ensure numeric values are valid
            try:
                line_item_data['impressions'] = float(line_item_data['impressions'])
                line_item_data['fcap'] = str(int(float(line_item_data['fcap'])))
            except (ValueError, TypeError):
                line_item_data['impressions'] = 0
                line_item_data['fcap'] = '0'

            # Ensure currency is valid
            if line_item_data['currency'] not in ['INR', 'USD', 'CAD', 'AED']:
                line_item_data['currency'] = 'INR'

            print(f"Validated line_item_data::{line_item_data}")

            client = get_ads_client()
            
            # Handle site filter exactly as in single_line.py
            site_filter = site if isinstance(site, list) else [site]
            if 'ALL_Languages' in site_filter:
                # Remove ALL_Languages and add specific sites
                site_filter = [s for s in site_filter if s != 'ALL_Languages']
                site_filter.extend(['IAG', 'ITBANGLA', 'MS', 'MT', 'NBT', 'TLG', 'TML', 'VK'])
                # Remove duplicates while preserving order
                site_filter = list(dict.fromkeys(site_filter))
                line_item_data['site'] = site_filter
            print(f"Processed sites: {site_filter}")

            # Fetch expresso details with timeout handling
            try:
                expresso_details = fetch_full_expresso_details(str(expresso_number))
                if expresso_details:
                    print(f"Expresso Details: {expresso_details}")
                    
                    campaign_package = expresso_details[0] if expresso_details else {}
                    matching_line_item = None
                    matching_package = None
                    
                    for package in expresso_details:
                        for line_item in package.get("LineItem_Details", []):
                            current_line_name = line_item.get("Line Item Name")
                            
                            # Try multiple matching strategies
                            matches = False
                            
                            # Strategy 1: Exact match
                            if current_line_name == line_name:
                                matches = True
                                print(f"✅ Exact name match: {current_line_name}")
                            
                            # Strategy 2: Check if input line_name is the Expresso name + site suffix
                            elif line_name.startswith(current_line_name + "_"):
                                matches = True
                                suffix = line_name[len(current_line_name)+1:]
                                print(f"✅ Expresso base + suffix match: {current_line_name} + _{suffix}")
                            
                            # Strategy 3: Base name comparison (original logic)
                            else:
                                current_line_name_base = current_line_name.split('_')[0] if '_' in current_line_name else current_line_name
                                input_line_name_base = line_name.split('_')[0] if '_' in line_name else line_name
                                
                                if current_line_name_base == input_line_name_base:
                                    matches = True
                                    print(f"✅ Base name match: {current_line_name_base}")
                            
                            if matches:
                                matching_line_item = line_item
                                matching_package = package
                                break
                    
                    if matching_line_item and matching_package:
                        line_item_data['CPM_Rate'] = matching_package.get('Gross Rate')
                        line_item_data['Start_date'] = matching_package.get('Package_StartDate')
                        line_item_data['End_date'] = matching_package.get('Package_EndDate')
                        line_item_data['expresso_line_item_found'] = True
                        line_item_data['expresso_line_item_name'] = matching_line_item.get("Line Item Name")
                        print(f"✅ Found matching line item in Expresso: {matching_line_item.get('Line Item Name')}")
                    else:
                        line_item_data['CPM_Rate'] = campaign_package.get('Gross Rate')
                        line_item_data['Start_date'] = campaign_package.get('Package_StartDate')
                        line_item_data['End_date'] = campaign_package.get('Package_EndDate')
                        line_item_data['expresso_line_item_found'] = False
                        print(f"ℹ️ No exact matching line item found in Expresso for: {line_name}")
            except Exception as e:
                print(f"Error fetching expresso details: {e}")
                return [dash.no_update] * 14 + [f"Error fetching expresso details: {str(e)}", True, None, dash.no_update]

            try:
                if not order_id or order_id == 'None' or order_id is None:
                    # Create new order name
                    order_name,advertiser_name,dsd_file_path=Dsd_Download(expresso_number)
                    trafficker_name = "Nitesh Pandey"
                    
                    # Get geo string - use "Multiple GEO" if more than one geo
                    geo_list = [g.strip() for g in geo_input.split(',') if g.strip()]
                    geo_str = geo_list[0] if len(geo_list) == 1 else "Multiple GEO"
                    
                    # Get package details from expresso data
                    package_id = None
                    start_date = None
                    if matching_package:
                        package_id = matching_package.get('Package Id')
                        start_date_str = matching_package.get('Package_StartDate')
                        if start_date_str:
                            try:
                                start_date = datetime.strptime(start_date_str, '%Y-%m-%d %H:%M:%S')
                            except Exception as e:
                                print(f"Error parsing start date: {e}")
                                start_date = datetime.now()
                    
                    # Use start date if available, otherwise use current date
                    if start_date:
                        order_day = start_date.strftime("%d")
                        order_month = start_date.strftime("%B")
                    else:
                        order_day = datetime.now().strftime("%d")
                        order_month = datetime.now().strftime("%B")
                    
                    # Add package ID to order name if available
                    package_str = f"{package_id}" if package_id else ""
                    new_order_name = f"{order_name}_{geo_str}_{order_day}_{order_month}_{package_str}"
                    # Create new order
                    order_id = create_order(client, advertiser_name, trafficker_name, new_order_name,line_item_data)  
                    print(f"Created new order with ID: {order_id}")
                
                # Create line item
                try:
                    line_id, creative_id = single_line(client, order_id, line_item_data, line_name)
                    print(f"Created line item with ID: {line_id}")
                    success_message = "Line item created successfully!"
                    # Check if creatives were created
                    if creative_id and len(creative_id) > 0:
                        success_message += f" Creatives: {len(creative_id)} created."
                    else:
                        success_message += " Note: No creatives were created (check creative files)."
                except LocationNotFoundError as e:
                    error_message = f"Location '{e.location_name}' is not found. Please enter it manually."
                    print(error_message)
                    
                    # Log location error
                    logger.log_line_creation_error(e, line_name, str(order_id), session_id)
                    
                    return [dash.no_update] * 14 + [error_message, True, None, dash.no_update]
                except Exception as e:
                    # Check if it's a creative creation error but line item was created
                    error_str = str(e)
                    if "line item" in error_str.lower() and "created" in error_str.lower():
                        success_message = "Line item created successfully! However, there was an issue with creative creation - please check the logs."
                        line_id = "Unknown"  # We'll still record the submission
                        
                        # Log partial success
                        logger.log_line_creation_success(
                            line_id=line_id,
                            creative_ids=[],
                            order_id=str(order_id),
                            line_name=line_name,
                            session_id=session_id
                        )
                    else:
                        # Log full error
                        logger.log_line_creation_error(e, line_name, str(order_id), session_id)
                        raise e  # Re-raise if it's a different error
                
                # Update submissions list
                sr_no = len(submissions) + 1
                time_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                submissions.append({
                    'sr': sr_no,
                    'user': email,
                    'expresso': expresso_number,
                    'gam_id': str(order_id),
                    'timestamp': time_str
                })
                
                # Log successful submission
                logger.log_line_creation_success(
                    line_id=str(line_id if 'line_id' in locals() else 'Unknown'),
                    creative_ids=creative_id if 'creative_id' in locals() and creative_id else [],
                    order_id=str(order_id),
                    line_name=line_name,
                    session_id=session_id
                )
                
                # Clean up files
                try:
                    expresso_id_str = str(expresso_number)
                    for pattern in [f"expresso_{expresso_id_str}_full_details.json", f"expresso_data_{expresso_id_str}.csv"]:
                        for file_path in glob.glob(pattern):
                            try:
                                os.unlink(file_path)
                                print(f"Removed file: {file_path}")
                            except Exception as e:
                                print(f"Warning: Error removing file {file_path}: {e}")
                except Exception as e:
                    print(f"Warning: Error in cleanup: {e}")
                
                return (
                    submissions,
                    dash.no_update,  # Keep email value
                    dash.no_update,  # Keep expresso value
                    dash.no_update,  # Keep label value
                    dash.no_update,  # Keep line_name value
                    dash.no_update,  # Keep site value
                    dash.no_update,  # Keep platform value
                    dash.no_update,  # Keep fcap value
                    dash.no_update,  # Keep currency value
                    dash.no_update,  # Keep impressions value
                    dash.no_update,  # Keep destination_url value
                    dash.no_update,  # Keep impression_tracker value
                    dash.no_update,  # Keep tracking_tag value
                    dash.no_update,  # Keep banner_video value
                    success_message,  # Success message with creative status
                    True,  # Show message
                    None,  # Clear upload status
                    stored_files  # Keep uploaded files
                )
                
            except Exception as e:
                error_message = f"Error creating line item: {str(e)}"
                print(error_message)
                return [dash.no_update] * 14 + [error_message, True, None, dash.no_update]
                
        except Exception as e:
            error_message = f"Error in submission: {str(e)}"
            print(error_message)
            return [dash.no_update] * 14 + [error_message, True, None, dash.no_update]
            
    return [dash.no_update] * 18





if __name__ == '__main__':
    app.run(debug=True) 
    print(f'submission::{submissions}')
    print(f"email id{handle_all_inputs.get('email')}")

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            * {
                margin: 0 !important;
                padding: 0 !important;
                box-sizing: border-box !important;
            }
            html, body {
                height: 100% !important;
                overflow-x: hidden !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            #react-entry-point {
                height: 100vh !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            .form-field, .Select-control, .Select--single, .Select-placeholder, .Select-value, .Select-input, .Select-menu-outer, .Select-menu {
                min-height: 40px !important;
                height: 40px !important;
                font-size: 1rem !important;
                border-radius: 8px !important;
                border: 1px solid #ced4da !important;
                background: #fff !important;
                box-shadow: 0 1px 4px rgba(0,0,0,0.04);
                padding-left: 12px !important;
                padding-right: 12px !important;
                box-sizing: border-box;
                display: flex;
                align-items: center;
            }
            input.form-field.form-control {
                line-height: 2 !important;
                height: 40px !important;
            }
            .Select-control {
                border: 1px solid #ced4da !important;
                background: #fff !important;
                box-shadow: 0 1px 4px rgba(0,0,0,0.04);
                padding-left: 12px !important;
                padding-right: 12px !important;
                min-height: 40px !important;
                height: 40px !important;
                border-radius: 8px !important;
                display: flex;
                align-items: center;
            }
            .Select-placeholder, .Select-value {
                font-size: 1rem !important;
                color: #6c757d !important;
                line-height: 2.0 !important;
            }
            .Select-arrow-zone {
                padding-top: 0 !important;
                padding-bottom: 0 !important;
                display: flex;
                align-items: center;
            }
            .Select-menu-outer {
                border-radius: 8px !important;
                font-size: 1rem !important;
            }
            .form-field:focus, .Select-control:focus {
                border-color: #2684ff !important;
                box-shadow: 0 0 0 2px rgba(38,132,255,0.2);
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''
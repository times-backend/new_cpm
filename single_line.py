import os
import glob
from googleads import ad_manager
from datetime import datetime
from ros_banner_template_creatives import create_custom_template_creatives
from placements_for_creatives import fetch_placements_ids
import sys
import requests
import hashlib
import base64
import json
import pandas as pd
import re
import traceback
from config import CREATIVES_FOLDER, CREDENTIALS_PATH
import time
import uuid
from logging_utils import logger

# Constants
SHEET_URL = "https://docs.google.com/spreadsheets/d/11_SZJnn5KALr6zi0JA27lKbmQvA1WSK4snp0UTY2AaY/edit?gid=2043018330"
PLACEMENT_SHEET_NAME_LANG = "ALL LANGUAGES"
PLACEMENT_SHEET_NAME_TOI = "TOI + ETIMES"
PLACEMENT_SHEET_NAME_ET = "ET Placement/Preset"

# Print sheet information for debugging
print(f"\nSheet Configuration:")
print(f"Sheet URL: {SHEET_URL}")
print(f"Language Sheet: {PLACEMENT_SHEET_NAME_LANG}")
print(f"TOI Sheet: {PLACEMENT_SHEET_NAME_TOI}")
print(f"ET Sheet: {PLACEMENT_SHEET_NAME_ET}")

# Create creatives folder if it doesn't exist
os.makedirs(CREATIVES_FOLDER, exist_ok=True)

available_presets = ["300x250", "320x50", "125x600", "300x600", "728x90", "980x200", "320x480","1260x570","728x500","1320x570","600x250","320x100"]

# Standard Banner Presets
standard_presets_dict = {
    "300x250": {"adtypes": ["MREC_ALL", "MREC", "MREC_1", "MREC_2", "MREC_3", "MREC_4", "MREC_5","BTF MREC"], "sections": ["ROS", "HP", "HOME"]},
    "320x50": {"adtypes": ["BOTTOMOVERLAY","BOTTOM OVERLAY"], "sections": ["ROS", "HP", "HOME"]},
    "300x600": {"adtypes": ["FLYINGCARPET", "FLYING_CARPET", "TOWER"], "sections": ["ROS", "HP", "HOME"]},
    "728x90": {"adtypes": ["LEADERBOARD"], "sections": ["ROS", "HP", "HOME"]},
    "980x200": {"adtypes": ["LEADERBOARD"], "sections": ["ROS"]},
    "320x480": {"adtypes": ["INTERSTITIAL"], "sections": ["ROS", "HP", "HOME"]},
    "1260x570": {"adtypes": ["INTERSTITIAL"], "sections": ["ROS", "HP", "HOME"]},
    "320x100": {"adtypes": ["SLUG1","SLUG2","SLUG3","SLUG4","SLUG5"], "sections": ["ROS", "HP", "HOME"]},
}

# Rich Media Presets
richmedia_presets_dict = {
    "300x250": {"adtypes": ["MREC_1"], "sections": ["ROS", "HP", "HOME"], "platforms": ["WEB"]},
    "320x100": {"adtypes": ["TOPBANNER", "TOPBANNER", "TOPBANNER" ], "sections": ["ROS", "HP", "HOME"], "platforms": ["MWEB"]},
    "300x600": {"adtypes": ["FLYINGCARPET", "FLYING_CARPET", "TOWER"], "sections": ["ROS", "HP", "HOME"], "platforms": ["WEB", "MWEB", "AMP"]},
    "728x90": {"adtypes": ["LEADERBOARD"], "sections": ["ROS", "HP", "HOME"], "platforms": ["WEB", "MWEB", "AMP"]},
    "320x50": {"adtypes": ["BOTTOMOVERLAY","BOTTOM OVERLAY"], "sections": ["ROS", "HP", "HOME"]},
    "320x480": {"adtypes": ["INTERSTITIAL"], "sections": ["ROS", "HP", "HOME"]},
    # ... add more as needed
}

class LocationNotFoundError(Exception):
    def __init__(self, location_name):
        super().__init__(f"No matching location found at any level for: {location_name}")
        self.location_name = location_name

def get_geo_id(client, location_name):
    """
    Hierarchical Geo ID search: Country → State/Region → City → Sub-District
    Returns the most specific matching Geo ID available
    """
    #print(f"🔍 Searching for Geo ID of: {location_name}")
    pql_service = client.GetService("PublisherQueryLanguageService", version="v202408")

    # Try as Country first
    country_query = f"""
    SELECT Id, Name, Targetable, Type, CountryCode 
    FROM Geo_Target 
    WHERE Name = '{location_name}' 
    AND Targetable = true 
    AND Type = 'COUNTRY'
    """
    
    # Try as State/Region if Country not found
    region_query = f"""
    SELECT Id, Name, Targetable, Type, CountryCode 
    FROM Geo_Target 
    WHERE Name = '{location_name}' 
    AND Targetable = true 
    AND Type IN ('REGION', 'PROVINCE', 'STATE', 'DEPARTMENT')
    AND CountryCode != 'PK'
    """
    
    # Try as City if neither Country nor Region found
    city_query = f"""
    SELECT Id, Name, Targetable, Type, CountryCode 
    FROM Geo_Target 
    WHERE Name = '{location_name}' 
    AND Targetable = true 
    AND Type = 'CITY'
    AND CountryCode != 'PK'
    """
    
    # Try as Sub-District 
    sub_district_query = f"""
    SELECT Id, Name, Targetable, Type, CountryCode 
    FROM Geo_Target 
    WHERE Name = '{location_name}' 
    AND Targetable = true 
    AND Type = 'SUB_DISTRICT'
    AND CountryCode != 'PK'
    """

    queries = [
        ("COUNTRY", country_query),
        ("REGION", region_query),
        ("CITY", city_query),
        ("SUB_DISTRICT", sub_district_query)
    ]

    for geo_type, query in queries:
        try:
            statement = {'query': query}
            response = pql_service.select(statement)
            
            if 'rows' in response and response['rows']:
                rows = response['rows']
                matches = []
                
                for row in rows:
                    values = row["values"]
                    geo_data = {
                        "Id": values[0]["value"],
                        "Name": values[1]["value"],
                        "Targetable": values[2]["value"],
                        "Type": values[3]["value"],
                        "CountryCode": values[4]["value"]
                    }
                    matches.append(geo_data)
                
                # Prioritize India (IN) and US locations
                india_matches = [m for m in matches if m["CountryCode"] == "IN"]
                us_matches = [m for m in matches if m["CountryCode"] == "US"]
                
                final_match = (
                    india_matches[0] if india_matches 
                    else us_matches[0] if us_matches 
                    else matches[0]
                )
                
                print(f"✅ Found as {geo_type}: {final_match['Name']}, {final_match['CountryCode']}, ID: {final_match['Id']}")
                return final_match["Id"]
                
        except Exception as e:
            print(f"⚠️ Error searching as {geo_type}: {e}")
            continue

    print(f"❌ No matching location found at any level for: {location_name}")
    raise LocationNotFoundError(location_name)


def fetch_images_and_presets(folder_path, available_presets, presets_dict):
    image_files = glob.glob(os.path.join(folder_path, "*.*"))
    detected_presets = {}
    image_size_map = {}  # Map to track images for each size
    
    # First, identify all valid images and their sizes
    for image_path in image_files:
        filename = os.path.basename(image_path)
        for preset in available_presets:
            if preset.lower() in filename.lower() and preset in presets_dict:
                if preset not in image_size_map:
                    image_size_map[preset] = []
                image_size_map[preset].append(image_path)
                
                # Create a unique key for each image of this size
                counter = len(image_size_map[preset])
                size_key = f"{preset}_{counter}" if counter > 1 else preset
                
                # Check if this is a 2x image
                is_2x = '2x' in filename.lower()
                
                detected_presets[size_key] = {
                    "adtype_filter": presets_dict[preset]["adtypes"],
                    "section_filter": presets_dict[preset]["sections"],
                    "image_path": image_path,
                    "base_size": preset,
                    "is_2x": is_2x
                }
                print(f"Added creative for size {preset} with key {size_key}: {filename} {'(2x density)' if is_2x else ''}")
    
    return detected_presets, image_files

def detect_line_type(line_name):
    if "RICHMEDIA" in line_name.upper():
        return "richmedia"
    else:
        return "standard"

def read_tag_file():
    """
    Reads a tag file (Excel format) that contains creative dimensions and their corresponding JavaScript tags.
    
    This function looks for files with names like 'tag.xlsx', 'tags.xlsx', 'tag.xls', or 'tags.xls'
    in both the current directory and the 'creatives' directory. If a file is found but can't be read,
    it falls back to creating a simulated tag dictionary.
    
    The function now supports:
    1. JavaScript tags (traditional script tags)
    2. Impression/click tag combinations
    3. DoubleClick tags (DCM tags with <ins> elements)
    
    Returns:
        dict: A dictionary mapping dimension strings to their corresponding JavaScript tags,
              or None if no valid tag file is found or an error occurs.
    """
    try:
        # Get the current directory where the script is running
        current_dir = os.path.dirname(os.path.abspath(__file__))
        creatives_dir = os.path.join(current_dir, "creatives")
        
        # Define possible tag file names
        tag_file_patterns = ['tag.xlsx', 'tags.xlsx', 'tag.xls', 'tags.xls', 'TOI Tags (2).xlsx', 'TOI Tags (2).xls']
        
        # First, try to find a real tag file
        real_tag_file = None
        real_tag_dir = None
        
        for directory in [current_dir, creatives_dir]:
            if not os.path.exists(directory):
                continue
                
            print(f"Checking directory for tag files: {directory}")
            for file in os.listdir(directory):
                file_lower = file.lower()
                if any(pattern.lower() in file_lower for pattern in tag_file_patterns):
                    real_tag_file = file
                    real_tag_dir = directory
                    print(f"Found potential tag file: {os.path.join(real_tag_dir, real_tag_file)}")
                    break
            
            if real_tag_file:
                break
                
        # If we found a real tag file, try to read it
        if real_tag_file:
            tag_file_path = os.path.join(real_tag_dir, real_tag_file)
            print(f"Attempting to read tag file at: {tag_file_path}")
            
            try:
                # For xlsx files, try pandas
                import pandas as pd
                
                def read_excel_with_sheet_selection(file_path, engine=None):
                    """Helper function to read Excel file with preference for 'tags' sheet"""
                    try:
                        # Try to read sheet names first
                        if engine:
                            excel_file = pd.ExcelFile(file_path, engine=engine)
                        else:
                            excel_file = pd.ExcelFile(file_path)
                        
                        sheet_names = excel_file.sheet_names
                        print(f"Available sheets: {sheet_names}")
                        
                        # Check for 'tags' sheet (case insensitive)
                        target_sheet = None
                        for sheet_name in sheet_names:
                            if sheet_name.lower() == 'tags':
                                target_sheet = sheet_name
                                print(f"Found 'tags' sheet: {target_sheet}")
                                break
                        
                        # If no 'tags' sheet found, use the first sheet
                        if target_sheet is None:
                            target_sheet = sheet_names[0]
                            print(f"No 'tags' sheet found, using first sheet: {target_sheet}")
                        
                        # Read the selected sheet
                        if engine:
                            df = pd.read_excel(file_path, sheet_name=target_sheet, engine=engine)
                        else:
                            df = pd.read_excel(file_path, sheet_name=target_sheet)
                        
                        return df
                    except Exception as e:
                        print(f"Error reading Excel file with sheet selection: {e}")
                        # Fallback to default behavior
                        if engine:
                            return pd.read_excel(file_path, engine=engine)
                        else:
                            return pd.read_excel(file_path)
                
                if tag_file_path.lower().endswith('.xlsx'):
                    df = read_excel_with_sheet_selection(tag_file_path)
                else:  # For xls files
                    try:
                        df = read_excel_with_sheet_selection(tag_file_path, engine='xlrd')
                    except:
                        try:
                            df = read_excel_with_sheet_selection(tag_file_path, engine='openpyxl')
                        except:
                            raise Exception(f"Failed to read {tag_file_path} with any Excel engine")
                
                print("\nDataFrame Info:")
                print(df.info())
                
                # Create a dictionary to store dimensions and their corresponding tags
                tag_dict = {}
                
                # Find column names for dimensions, JavaScript tags, Impression Tags and Click Tags
                dimension_col = None
                tag_col = None
                impression_tag_col = None
                click_tag_col = None
                
                print(f"Available columns: {list(df.columns)}")
                
                # Look for exact column names first
                for col in df.columns:
                    col_str = str(col).lower()
                    if col_str == 'dimensions' or col_str == 'placementname':
                        dimension_col = col
                        print(f"Using exact match '{col}' as dimension column")
                    elif col_str == 'javascript tag' or col_str == 'js_https':
                        tag_col = col
                        print(f"Using exact match '{col}' as tag column")
                    elif col_str == 'impression tag (image)' or col_str == 'impression tag':
                        impression_tag_col = col
                        print(f"Using exact match '{col}' as impression tag column")
                    elif col_str == 'click tag':
                        click_tag_col = col
                        print(f"Using exact match '{col}' as click tag column")
                        
                
                # If needed, look for partial matches
                if not dimension_col:
                    for col in df.columns:
                        col_str = str(col).lower()
                        if 'dimension' in col_str or 'size' in col_str or 'placement' in col_str:
                            dimension_col = col
                            print(f"Using partial match '{col}' as dimension column")
                            break
                
                if not tag_col:
                    for col in df.columns:
                        col_str = str(col).lower()
                        if ('javascript' in col_str and 'tag' in col_str) or 'script' in col_str or 'js_' in col_str:
                            tag_col = col
                            print(f"Using partial match '{col}' as tag column")
                            break
                
                if not impression_tag_col:
                    for col in df.columns:
                        col_str = str(col).lower()
                        if 'impression' in col_str and 'tag' in col_str:
                            impression_tag_col = col
                            print(f"Using partial match '{col}' as impression tag column")
                            break
                
                if not click_tag_col:
                    for col in df.columns:
                        col_str = str(col).lower()
                        if 'click' in col_str and 'tag' in col_str:
                            click_tag_col = col
                            print(f"Using partial match '{col}' as click tag column")
                            break
                
                # Final attempt to find tag column
                if dimension_col and not tag_col and not (impression_tag_col and click_tag_col):
                    for col in df.columns:
                        col_str = str(col).lower()
                        if 'tag' in col_str:
                            tag_col = col
                            print(f"Using fallback '{col}' as tag column")
                            break
                
                has_columns = dimension_col and (tag_col or (impression_tag_col and click_tag_col))
                
                if has_columns:
                    # Process the dataframe
                    for index, row in df.iterrows():
                        if pd.notnull(row[dimension_col]):
                            dimension = str(row[dimension_col]).strip()
                            
                            # Check for Impression Tag and Click Tag first (new priority)
                            if impression_tag_col and click_tag_col and pd.notnull(row[impression_tag_col]) and pd.notnull(row[click_tag_col]):
                                impression_tag = str(row[impression_tag_col]).strip()
                                click_tag = str(row[click_tag_col]).strip()
                                
                                # Skip empty entries
                                if not dimension or not impression_tag or not click_tag:
                                    continue
                                
                                # Clean up dimension string to ensure format like "300x250"
                                if 'x' in dimension:
                                    dimension_match = re.search(r'(\d+x\d+)', dimension)
                                    if dimension_match:
                                        dimension = dimension_match.group(1)
                                
                                # Store both tags in a dictionary
                                tag_dict[dimension] = {
                                    'type': 'impression_click',
                                    'impression_tag': impression_tag,
                                    'click_tag': click_tag
                                }
                                print(f"Added impression/click tags for dimension: {dimension}")
                            
                            # Fallback to JavaScript tag if impression/click tags not found
                            elif tag_col and pd.notnull(row[tag_col]):
                                js_tag = str(row[tag_col]).strip()
                                
                                # Skip empty entries
                                if not dimension or not js_tag:
                                    continue
                                    
                                # Clean up dimension string to ensure format like "300x250"
                                if 'x' in dimension:
                                    dimension_match = re.search(r'(\d+x\d+)', dimension)
                                    if dimension_match:
                                        dimension = dimension_match.group(1)
                                
                                # Handle <noscript> tags with <a> href, common in Flashtalking tags
                                if '<noscript>' in js_tag.lower() and '<a href' in js_tag.lower():
                                    print(f"Detected noscript/a href tag for dimension: {dimension}")
                                    href_pattern = r'(<a\s+[^>]*?href=")([^"]*)"'
                                    
                                    # Prepend click macro if not already present
                                    if '%%CLICK_URL_UNESC%%' not in js_tag:
                                        replacement = r'\1%%CLICK_URL_UNESC%%\2"'
                                        modified_tag = re.sub(href_pattern, replacement, js_tag, flags=re.IGNORECASE)
                                        
                                        if modified_tag != js_tag:
                                            js_tag = modified_tag
                                            print(f"Added %%CLICK_URL_UNESC%% to href in noscript tag for dimension: {dimension}")
                                        else:
                                            print(f"Warning: Could not add %%CLICK_URL_UNESC%% to href for dimension: {dimension}")
                                    else:
                                        print(f"Click macro already present for dimension: {dimension}")

                                # Check if this is a DoubleClick tag (contains dcmads or data-dcm attributes)
                                is_doubleclick = False
                                if ('dcmads' in js_tag.lower() or 'data-dcm' in js_tag.lower()) and ('<ins' in js_tag.lower() or '<div' in js_tag.lower()):
                                    is_doubleclick = True
                                    print(f"Detected DoubleClick tag for dimension: {dimension}")
                                    
                                    # Ensure data-dcm-click-tracker is present in the DoubleClick tag
                                    if 'data-dcm-click-tracker' not in js_tag:
                                        try:
                                            # Add data-dcm-click-tracker attribute before the class attribute
                                            tag_pattern = r'(<ins|<div)([^>]*?)(\s+class=)'
                                            replacement = r"\1\2 data-dcm-click-tracker='%%CLICK_URL_UNESC%%'\3"
                                            modified_tag = re.sub(tag_pattern, replacement, js_tag, flags=re.IGNORECASE)
                                            
                                            # If that didn't work, try adding it after the opening tag
                                            if modified_tag == js_tag:
                                                tag_pattern = r'(<ins|<div)(\s)'
                                                replacement = r"\1 data-dcm-click-tracker='%%CLICK_URL_UNESC%%'\2"
                                                modified_tag = re.sub(tag_pattern, replacement, js_tag, flags=re.IGNORECASE)
                                            
                                            js_tag = modified_tag
                                            print(f"Added data-dcm-click-tracker attribute to DoubleClick tag for dimension: {dimension}")
                                        except Exception as e:
                                            print(f"Warning: Could not add data-dcm-click-tracker to tag: {str(e)}")
                                
                                # Only add if tag is substantial
                                if 'x' in dimension and len(js_tag.strip()) > 10:
                                    # Check if this dimension already exists in the dictionary
                                    if dimension in tag_dict:
                                        # It's a duplicate, so append a counter
                                        counter = 1
                                        while f"{dimension}_{counter}" in tag_dict:
                                            counter += 1
                                        dimension_key = f"{dimension}_{counter}"
                                        print(f"Found duplicate dimension {dimension}, using key {dimension_key}")
                                    else:
                                        dimension_key = dimension
                                    
                                    if is_doubleclick:
                                        tag_dict[dimension_key] = {
                                            'type': 'doubleclick',
                                            'js_tag': js_tag
                                        }
                                        print(f"Added DoubleClick tag for dimension: {dimension}")
                                    else:
                                        tag_dict[dimension_key] = {
                                            'type': 'javascript',
                                            'js_tag': js_tag
                                        }
                                        print(f"Added JavaScript tag for dimension: {dimension}")
                    
                    if tag_dict:
                        print(f"Successfully read {len(tag_dict)} tags from {real_tag_file}")
                        return tag_dict
                    else:
                        print(f"No valid tag entries found in {real_tag_file}")
                else:
                    print(f"Couldn't find required columns in {real_tag_file}. Found columns: {list(df.columns)}")
                    print("Looking for columns named 'Dimensions' or 'PlacementName' and either 'JavaScript Tag' or 'js_https'")
            
            except Exception as e:
                print(f"Error reading file {real_tag_file}: {str(e)}")
                traceback.print_exc()
        
        # If we didn't find or couldn't read a real tag file, fall back to simulated dictionary
        print("No valid tag file found. Not creating simulated tags.")
        return None
        
    except Exception as e:
        print(f"Error in read_tag_file: {str(e)}")
        print(f"Error type: {type(e)}")
        traceback.print_exc()
        return None

def check_line_item_name_exists(client, order_id, line_name_base):
    """Check if a line item with similar name already exists in the order or globally"""
    try:
        line_item_service = client.GetService('LineItemService', version='v202408')
        pql_service = client.GetService('PublisherQueryLanguageService', version='v202408')
        
        # Clean the line name to ensure consistency
        cleaned_line_name = line_name_base.strip() if line_name_base else ''
        print(f"🔍 Checking for duplicates of line name: '{cleaned_line_name}'")
        print(f"🔍 Line name length: {len(cleaned_line_name)} characters")
        
        # Escape single quotes in the line name for PQL query
        escaped_line_name = cleaned_line_name.replace("'", "\\'")
        
        # First check for exact matches globally (this is what causes DUPLICATE_OBJECT error)
        exact_query = f"SELECT Id, Name, OrderId FROM Line_Item WHERE Name = '{escaped_line_name}'"
        print(f"🔍 Executing exact match query: {exact_query}")
        exact_statement = {'query': exact_query}
        exact_response = pql_service.select(exact_statement)
        
        print(f"🔍 Exact query response type: {type(exact_response)}")
        if hasattr(exact_response, 'rows') and exact_response.rows:
            print(f"🔍 Exact query found {len(exact_response.rows)} rows")
            existing_exact = [(row.values[0].value, row.values[1].value, row.values[2].value) 
                             for row in exact_response.rows]
            print(f"⚠️ Found {len(existing_exact)} existing line items with EXACT name '{line_name_base}':")
            for line_id, name, existing_order_id in existing_exact:
                print(f"   - Line ID: {line_id}, Name: {name}, Order ID: {existing_order_id}")
            return True
        else:
            print(f"🔍 No rows found in exact query response")
        
        # Also check for the original name if it was different from cleaned name
        if line_name_base != cleaned_line_name:
            original_escaped = line_name_base.replace("'", "\\'")
            original_query = f"SELECT Id, Name, OrderId FROM Line_Item WHERE Name = '{original_escaped}'"
            print(f"🔍 Executing original name query: {original_query}")
            original_statement = {'query': original_query}
            original_response = pql_service.select(original_statement)
            
            if hasattr(original_response, 'rows') and original_response.rows:
                print(f"🔍 Original name query found {len(original_response.rows)} rows")
                existing_original = [(row.values[0].value, row.values[1].value, row.values[2].value) 
                                   for row in original_response.rows]
                print(f"⚠️ Found {len(existing_original)} existing line items with ORIGINAL name '{line_name_base}':")
                for line_id, name, existing_order_id in existing_original:
                    print(f"   - Line ID: {line_id}, Name: {name}, Order ID: {existing_order_id}")
                return True
        
        # Also try a broader search to catch any similar names
        # Use LIKE with wildcards to find potential matches
        like_query = f"SELECT Id, Name, OrderId FROM Line_Item WHERE Name LIKE '%{escaped_line_name}%'"
        print(f"🔍 Executing LIKE query: {like_query}")
        like_statement = {'query': like_query}
        like_response = pql_service.select(like_statement)
        
        print(f"🔍 LIKE query response type: {type(like_response)}")
        if hasattr(like_response, 'rows') and like_response.rows:
            print(f"🔍 LIKE query found {len(like_response.rows)} rows")
            existing_like = [(row.values[0].value, row.values[1].value, row.values[2].value) 
                           for row in like_response.rows]
            print(f"⚠️ Found {len(existing_like)} existing line items with SIMILAR names to '{line_name_base}':")
            for line_id, name, existing_order_id in existing_like:
                print(f"   - Line ID: {line_id}, Name: {name}, Order ID: {existing_order_id}")
                # Check if it's an exact match
                if name == line_name_base:
                    print(f"   ⚠️ EXACT MATCH FOUND: This will cause DUPLICATE_OBJECT error!")
                    return True
        
        # Then check for similar names in the same order (for good measure)
        similar_query = f"SELECT Id, Name FROM Line_Item WHERE OrderId = {order_id} AND Name LIKE '{escaped_line_name}%'"
        print(f"🔍 Executing order-specific query: {similar_query}")
        similar_statement = {'query': similar_query}
        similar_response = pql_service.select(similar_statement)
        
        if hasattr(similar_response, 'rows') and similar_response.rows:
            existing_similar = [row.values[1].value for row in similar_response.rows]
            print(f"⚠️ Found {len(existing_similar)} existing line items with similar names in order {order_id}: {existing_similar}")
            # Check for exact matches in this order too
            for existing_name in existing_similar:
                if existing_name == cleaned_line_name or existing_name == line_name_base:
                    print(f"   ⚠️ EXACT MATCH in same order: This will cause DUPLICATE_OBJECT error!")
                    return True
        
        # Additional comprehensive search - try different query approaches
        print(f"🔍 Performing comprehensive search for potential duplicates...")
        
        # Try searching without LIKE operators to catch exact matches that might be missed
        # Also check for soft-deleted items and different status conditions
        comprehensive_queries = [
            f"SELECT Id, Name, OrderId, Status FROM Line_Item WHERE Name = '{escaped_line_name}' LIMIT 10",
            f"SELECT Id, Name, OrderId, Status FROM Line_Item WHERE OrderId = {order_id} LIMIT 100",
            f"SELECT Id, Name, OrderId, Status FROM Line_Item WHERE Name = '{escaped_line_name}' AND Status IN ('ACTIVE', 'PAUSED', 'INACTIVE') LIMIT 10",
            # Check total count in order - PQL requires column names for COUNT
            f"SELECT COUNT(Id) AS count FROM Line_Item WHERE OrderId = {order_id}",
            # Check for any line items with same targeting
            f"SELECT Id, Name FROM Line_Item WHERE OrderId = {order_id} AND Id IN (SELECT LineItemId FROM LineItemTargeting)"
        ]
        
        for i, comp_query in enumerate(comprehensive_queries):
            try:
                print(f"🔍 Executing comprehensive query {i+1}: {comp_query}")
                comp_statement = {'query': comp_query}
                comp_response = pql_service.select(comp_statement)
                
                if hasattr(comp_response, 'rows') and comp_response.rows:
                    print(f"🔍 Comprehensive query {i+1} found {len(comp_response.rows)} rows")
                    for row in comp_response.rows:
                        existing_name = row.values[1].value
                        existing_order_id = row.values[2].value if len(row.values) > 2 else 'Unknown'
                        existing_status = row.values[3].value if len(row.values) > 3 else 'Unknown'
                        
                        # Check for exact match with cleaned name or original name
                        if existing_name == cleaned_line_name or existing_name == line_name_base:
                            print(f"   ⚠️ COMPREHENSIVE SEARCH FOUND EXACT MATCH!")
                            print(f"   - Existing Name: '{existing_name}'")
                            print(f"   - Target Name: '{cleaned_line_name}'")
                            print(f"   - Order ID: {existing_order_id}")
                            print(f"   - Status: {existing_status}")
                            return True
                else:
                    print(f"🔍 Comprehensive query {i+1} found no rows")
            except Exception as e:
                print(f"⚠️ Error in comprehensive query {i+1}: {e}")
        
        print(f"✅ No existing line items found with exact or similar name: {cleaned_line_name}")
        return False
        
    except Exception as e:
        print(f"⚠️ Error checking for existing line item names: {e}")
        print(f"⚠️ Error type: {type(e).__name__}")
        print(f"⚠️ Will continue with creation but may encounter DUPLICATE_OBJECT error")
        return False  # Continue with creation if check fails





def single_line(client, order_id, line_item_data, line_name):
    # Import modules needed for retry logic
    import random
    import uuid
    import string
    
    # Generate session ID for this line creation
    session_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Initialize timing checkpoints
    timing_checkpoints = {
        'start_time': start_time,
        'data_processing_start': None,
        'data_processing_end': None,
        'placement_lookup_start': None,
        'placement_lookup_end': None,
        'line_creation_start': None,
        'line_creation_end': None,
        'creative_creation_start': None,
        'creative_creation_end': None
    }
    
    # Log line creation start
    logger.log_line_creation_start(str(order_id), line_item_data, line_name, session_id)
    
    line_item_service = client.GetService('LineItemService', version='v202408')
    
    # Track created creatives by size to prevent duplicates
    created_creative_sizes = set()
    
    def track_creative_creation(size, creative_ids_list):
        """Track created creatives to prevent duplicates"""
        if creative_ids_list:
            created_creative_sizes.add(size)
            print(f"📝 Tracked creative creation: {size} -> {len(creative_ids_list)} creatives")
    
    def is_creative_size_already_created(size):
        """Check if a creative of this size has already been created"""
        return size in created_creative_sizes

    end_date_value = line_item_data.get('End_date')
    print(f"end_date_value::{end_date_value}")
    start_date_value = line_item_data.get('Start_date', '2025-05-06 00:00:00')
    print(f"start_date_value::{start_date_value}")
    Fcap_value = int(line_item_data.get('fcap', 0))
    cost = line_item_data.get('CPM_Rate', line_item_data.get('cpm', 0))
    print(f"line_item_data::{line_item_data}")
    
    # Start data processing timing
    timing_checkpoints['data_processing_start'] = time.time()
    
    # End data processing timing
    timing_checkpoints['data_processing_end'] = time.time()
    
    # Process impression value to ensure it's an integer
    total_impressions = line_item_data.get('impressions', 100000)
    try:
        if isinstance(total_impressions, str):
            total_impressions = float(total_impressions.replace(',', ''))
        elif isinstance(total_impressions, float):
            pass
        else:
            total_impressions = float(total_impressions)
        impressions_int = int(total_impressions)
        print(f"Total impressions converted to integer: {impressions_int}")
    except Exception as e:
        print(f"Error converting impressions to integer: {e}. Using default value.")
        impressions_int = 100000

    # Extract year, month, and date from end_date_value
    try:
        if isinstance(end_date_value, str) and '-' in end_date_value and ':' in end_date_value:
            date_parts = end_date_value.split(' ')[0].split('-')
            year = int(date_parts[0])
            month = int(date_parts[1])
            day = int(date_parts[2])
            
            print(f"year::{year}, month::{month}, day::{day}")
            if ' ' in end_date_value and ':' in end_date_value:
                time_parts = end_date_value.split(' ')[1].split(':')
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                second = int(time_parts[2]) if len(time_parts) > 2 else 0
            else:
                hour, minute, second = 23, 59, 0
        else:
            year, month, day = 2025, 12, 31
            hour, minute, second = 23, 59, 0
            
        structured_end_date = {
            'date': {
                'year': year,
                'month': month,
                'day': day
            },
            'hour': hour,
            'minute': minute,
            'second': second,
            'timeZoneId': 'Asia/Kolkata'
        }
        
        print(f"Extracted date components - Year: {year}, Month: {month}, Day: {day}")
        print(f"Structured end date for API: {structured_end_date}")

        if isinstance(start_date_value, str) and '-' in start_date_value and ':' in start_date_value:
            date_parts = start_date_value.split(' ')[0].split('-')
            start_year = int(date_parts[0])
            start_month = int(date_parts[1])
            start_day = int(date_parts[2])
            
            current_date = datetime.now()
            start_date = datetime(start_year, start_month, start_day)
            
            if start_date.date() <= current_date.date():
                print("Start date is today or in the past, using IMMEDIATELY")
                use_start_date_type = True
                structured_start_date = None
            else:
                print("Start date is in the future, using structured date with 00:00:00")
                use_start_date_type = False
                structured_start_date = {
                    'date': {
                        'year': start_year,
                        'month': start_month,
                        'day': start_day
                    },
                    'hour': 0,
                    'minute': 0,
                    'second': 0,
                    'timeZoneId': 'Asia/Kolkata'
                }
                print(f"Structured start date for API: {structured_start_date}")
        else:
            print("No valid start date provided, using IMMEDIATELY")
            use_start_date_type = True
            structured_start_date = None
            
    except Exception as e:
        print(f"Error extracting date components: {e}. Using default dates.")
        structured_end_date = {
            'date': {
                'year': 2025,
                'month': 12,
                'day': 31
            },
            'hour': 23,
            'minute': 59,
            'second': 0,
            'timeZoneId': 'Asia/Kolkata'
        }
        
        current_date = datetime.now()
        structured_start_date = {
            'date': {
                'year': current_date.year,
                'month': current_date.month,
                'day': current_date.day
            },
            'hour': current_date.hour,
            'minute': current_date.minute,
            'second': current_date.second,
            'timeZoneId': 'Asia/Kolkata'
        }

    geo_targeting_input = line_item_data.get("geoTargeting", line_item_data.get("geo", []))
    if isinstance(geo_targeting_input, str):
        geo_targeting_input = [city.strip() for city in geo_targeting_input.split(",") if city.strip()]
    elif isinstance(geo_targeting_input, list):
        geo_targeting_input = [str(city).strip() for city in geo_targeting_input if str(city).strip()]
    
    print(f"Processing geo targeting: {geo_targeting_input}")
    geo_targeting_ids = []
    
    invalid_locations = []
    for city in geo_targeting_input:
        try:
            geo_id = get_geo_id(client, city)
            if geo_id:
                geo_targeting_ids.append(geo_id)
                print(f"Found geo ID {geo_id} for {city}")
        except LocationNotFoundError as e:
            print(f"Warning: {e}")
            invalid_locations.append(city)
    
    if not geo_targeting_ids:
        print("Warning: No valid geo targeting IDs found. Line item will target all locations.")
        # Proceed with empty geo_targeting_ids (targets all locations)

    destination_url = line_item_data.get('destination_url', '') or ''
    expresso_id = str(line_item_data.get('expresso_id', ''))
    landing_page = (line_item_data.get('landing_page', '') or line_item_data.get('destination_url', '')) or ''
    Template_Id = line_item_data.get('Template_id', '')
    impression_tracker = (line_item_data.get('impression_tracker') or '').strip()
    script_tracker = (line_item_data.get('tracking_tag') or '').strip()
    currency = (line_item_data.get('currency') or 'INR').strip().upper()
    In_Banner_video = line_item_data.get('banner_video', '')
    
    # Replace [timestamp] with %%CACHEBUSTER%% in impression_tracker
    if impression_tracker:
        original_impression_tracker = impression_tracker
        impression_tracker = impression_tracker.replace('[timestamp]', '%%CACHEBUSTER%%').replace('[CACHEBUSTER]', '%%CACHEBUSTER%%')
        if original_impression_tracker != impression_tracker:
            print(f"Replaced timestamp in impression_tracker: {original_impression_tracker} -> {impression_tracker}")
    
    # Replace [timestamp] with %%CACHEBUSTER%% in script_tracker
    if script_tracker:
        original_script_tracker = script_tracker
        script_tracker = script_tracker.replace('[timestamp]', '%%CACHEBUSTER%%').replace('[CACHEBUSTER]', '%%CACHEBUSTER%%')
        if original_script_tracker != script_tracker:
            print(f"Replaced timestamp in script_tracker: {original_script_tracker} -> {script_tracker}")

    # Ensure strings are not None before strip()
    destination_url = str(destination_url) if destination_url is not None else ''
    landing_page = str(landing_page) if landing_page is not None else ''

    # Check if landing page and destination URL are both empty
    if not landing_page.strip() and not destination_url.strip():
        # Default to 12399020, but we'll check for 2x images later and potentially change to 12473441
        print("No landing page or destination URL provided. Will determine template based on image names.")
        Template_Id = 12399020  # Default, may be updated later
        landing_page = ''
        destination_url = ''
    elif not Template_Id or Template_Id == '':
        # If there's a landing page or destination URL but no explicit template, use standard template
        print("Landing page/destination URL provided. Using standard template 12330939.")
        Template_Id = 12330939
    
    if currency not in ['INR', 'USD', 'CAD', 'AED']:
        currency = 'INR'
    
    print(f"Processed values:")
    print(f"destination_url: {destination_url}")
    print(f"expresso_id: {expresso_id}")
    print(f"landing_page: {landing_page}")
    print(f"Template_Id: {Template_Id}")
    print(f"impression_tracker: {impression_tracker}")
    print(f"script_tracker: {script_tracker}")
    print(f"currency: {currency}")
    print(f"In_Banner_video: {In_Banner_video}")
    
    if script_tracker:
        script_tracker = f'<div style="display:none;">{script_tracker}</div>'
   
    line_type = detect_line_type(line_name)
    print(f"line_type:::{line_type}")
    if line_type == "richmedia":
        presets_dict = richmedia_presets_dict
    else:
        presets_dict = standard_presets_dict

    # First check if tag file exists
    tag_dict = read_tag_file()
    
    if tag_dict:
        print("Found tag file, will use both tag-based and placement-based targeting")
        detected_creatives = {}
        
        # Create detected_creatives based on available tag sizes
        for size in tag_dict.keys():
            if 'x' in size:
                base_size = size.split('_')[0].strip()
                if base_size in available_presets and base_size in presets_dict:
                    # For richmedia lines, check platform compatibility
                    if line_type == "richmedia":
                        required_platforms = presets_dict[base_size].get("platforms", [])
                        current_platforms = [p.strip().upper() for p in line_item_data['platforms']]
                        
                        # Check if any of the current platforms match the required platforms
                        platform_match = any(platform in required_platforms for platform in current_platforms)
                        
                        if not platform_match:
                            print(f"🚫 Skipping tag size {base_size} - platform mismatch. Required: {required_platforms}, Current: {current_platforms}")
                            continue
                        else:
                            print(f"✅ Tag size {base_size} platform match. Required: {required_platforms}, Current: {current_platforms}")
                    
                    size_key = size
                    detected_creatives[size_key] = {
                        "adtype_filter": presets_dict[base_size]["adtypes"],
                        "section_filter": presets_dict[base_size]["sections"],
                        "base_size": base_size
                    }
                    print(f"Added size {size_key} from tag file")
    else:
        print("No tag file found, using Google Sheets for placement targeting")
        detected_creatives, image_files = fetch_images_and_presets(CREATIVES_FOLDER, available_presets, presets_dict)
        
        if not detected_creatives:
            if In_Banner_video and In_Banner_video.strip():
                print(f"No image creatives detected, but In_Banner_video is provided: {In_Banner_video}")
                detected_creatives["300x250"] = {
                    "adtype_filter": presets_dict["300x250"]["adtypes"] if "300x250" in presets_dict else ["MREC_ALL", "MREC"],
                    "section_filter": presets_dict["300x250"]["sections"] if "300x250" in presets_dict else ["ROS", "HP"],
                    "base_size": "300x250"
                }
                print("Added 300x250 size for In-Banner Video to detected_creatives")
            else:
                raise ValueError("No creatives detected in the creatives folder and no valid tag file found.")

    print(f"Final Template_Id: {Template_Id}")

    # Group creatives by base size for placement targeting
    size_groups = {}
    for size_key, creative_info in detected_creatives.items():
        base_size = creative_info.get('base_size', size_key.split('_')[0])
        
        # For richmedia lines, check platform compatibility
        if line_type == "richmedia" and base_size in presets_dict:
            required_platforms = presets_dict[base_size].get("platforms", [])
            current_platforms = [p.strip().upper() for p in line_item_data['platforms']]
            
            # Check if any of the current platforms match the required platforms
            platform_match = any(platform in required_platforms for platform in current_platforms)
            
            if not platform_match:
                print(f"🚫 Skipping size {base_size} - platform mismatch. Required: {required_platforms}, Current: {current_platforms}")
                continue
            else:
                print(f"✅ Size {base_size} platform match. Required: {required_platforms}, Current: {current_platforms}")
        
        # Special case: if size is 320x100, use 320x50 for placement targeting
        placement_size = "320x50" if base_size == "320x100" else base_size
        
        if placement_size not in size_groups:
            # Use the original base_size for adtype and section filters
            filter_size = base_size if base_size in presets_dict else placement_size
            size_groups[placement_size] = {
                "adtype_filter": presets_dict[filter_size]["adtypes"] if filter_size in presets_dict else creative_info["adtype_filter"],
                "section_filter": presets_dict[filter_size]["sections"] if filter_size in presets_dict else creative_info["section_filter"],
                "placement_ids": [],
                "original_sizes": [base_size]  # Track original sizes for this placement group
            }
        else:
            # Add this original size to the existing group
            if "original_sizes" not in size_groups[placement_size]:
                size_groups[placement_size]["original_sizes"] = []
            if base_size not in size_groups[placement_size]["original_sizes"]:
                size_groups[placement_size]["original_sizes"].append(base_size)

    site_filter = line_item_data['site']
    if isinstance(site_filter, str):
        site_filter = [site_filter]

    print("\n🔍 Input values:")
    print(f"Site filter: {site_filter}")
    print(f"Platforms: {line_item_data['platforms']}")

    # Normalize platforms to uppercase for consistent matching
    normalized_platforms = [p.strip().upper() for p in line_item_data['platforms']]
    print(f"Normalized platforms: {normalized_platforms}")

    if 'ALL_Languages' in site_filter:
        site_filter = [site for site in site_filter if site != 'ALL_Languages']
        site_filter.extend(['IAG', 'ITBANGLA', 'MS', 'MT', 'NBT', 'TLG', 'TML', 'VK'])
        site_filter = list(dict.fromkeys(site_filter))
        print(f"Expanded ALL_Languages to: {site_filter}")

    contains_toi = any(site in ['TOI', 'ETIMES'] for site in site_filter)
    contains_et = any(site == 'ET' for site in site_filter)
    
    # Log placement targeting configuration
    logger.log_placement_targeting({
        'site_filter': site_filter,
        'platform_filter': normalized_platforms,
        'contains_toi': contains_toi,
        'contains_et': contains_et
    }, session_id)
    contains_lang = any(site not in ['TOI', 'ETIMES', 'ET'] for site in site_filter)

    print("\n📊 Site categorization:")
    print(f"Contains TOI/ETIMES: {contains_toi}")
    print(f"Contains ET: {contains_et}")
    print(f"Contains other languages: {contains_lang}")

    placement_data = {}

    # For richmedia lines, create platform mapping for each size
    filtered_size_groups = {}
    richmedia_platform_map = {}
    
    if line_type == "richmedia":
        for size_key, size_info in size_groups.items():
            # Get the original sizes for this group
            original_sizes = size_info.get('original_sizes', [size_key])
            
            # For each original size, check what platforms it supports
            all_supported_platforms = set()
            for orig_size in original_sizes:
                if orig_size in presets_dict:
                    size_platforms = [p.upper() for p in presets_dict[orig_size].get('platforms', [])]
                    # Only use platforms that are both in input and supported by this size
                    supported_for_this_size = set(normalized_platforms).intersection(set(size_platforms))
                    all_supported_platforms.update(supported_for_this_size)
                    print(f"📋 Size {orig_size} supports platforms: {size_platforms}, effective: {list(supported_for_this_size)}")
            
            # Only include this size group if it has supported platforms
            if all_supported_platforms:
                filtered_size_groups[size_key] = size_info.copy()
                richmedia_platform_map[size_key] = list(all_supported_platforms)
                print(f"✅ Size group {size_key} (richmedia) will use platforms: {list(all_supported_platforms)}")
            else:
                print(f"🚫 Size group {size_key} (richmedia) has no supported platforms, skipping")
    else:
        filtered_size_groups = size_groups
        richmedia_platform_map = None
    
    # Use user-specified platforms for both richmedia and standard lines
    platforms_for_fetch = normalized_platforms
    print(f"🎯 Using user-specified platforms for placement fetch: {platforms_for_fetch}")

    # End data processing, start placement lookup timing
    timing_checkpoints['data_processing_end'] = time.time()
    timing_checkpoints['placement_lookup_start'] = time.time()

    # Always fetch placements regardless of tag file
    if contains_toi:
        toi_sites = [s for s in site_filter if s in ['TOI', 'ETIMES']]
        print("\nFetching TOI placements:")
        
        placement_data_toi = fetch_placements_ids(
            CREDENTIALS_PATH,
            SHEET_URL,
            PLACEMENT_SHEET_NAME_TOI,
            toi_sites,
            platforms_for_fetch,
            filtered_size_groups,
            richmedia_platform_map,
            line_type
        )
        # Merge TOI placement data
        print(f"🔍 TOI placement_data_toi type: {type(placement_data_toi)}")
        print(f"🔍 TOI placement_data_toi content: {placement_data_toi}")
        
        for size, data in placement_data_toi.items():
            print(f"🔍 TOI merging - Size: {size}, Data type: {type(data)}, Data: {data}")
            if size not in placement_data:
                placement_data[size] = data.copy()
                print(f"🔍 TOI - Added new size {size} to placement_data")
            else:
                # Ensure we're working with dictionaries
                if not isinstance(placement_data[size], dict):
                    print(f"⚠️ TOI - placement_data[{size}] is not a dict: {type(placement_data[size])}")
                    placement_data[size] = {}
                if not isinstance(data, dict):
                    print(f"⚠️ TOI - incoming data is not a dict: {type(data)}")
                    continue
                    
                # Combine placement IDs from both sources
                existing_ids = set(placement_data[size].get('placement_ids', []))
                new_ids = set(data.get('placement_ids', []))
                placement_data[size]['placement_ids'] = list(existing_ids | new_ids)
                
                # Preserve original_sizes information
                existing_original_sizes = set(placement_data[size].get('original_sizes', []))
                new_original_sizes = set(data.get('original_sizes', []))
                placement_data[size]['original_sizes'] = list(existing_original_sizes | new_original_sizes)
                
                print(f"🔄 Merged TOI placements for {size}: {len(new_ids)} new IDs")

    if contains_et:
        et_sites = [s for s in site_filter if s == 'ET']
        print("\nFetching ET placements:")
        placement_data_et = fetch_placements_ids(
            CREDENTIALS_PATH,
            SHEET_URL,
            PLACEMENT_SHEET_NAME_ET,
            et_sites,
            platforms_for_fetch,
            filtered_size_groups,
            richmedia_platform_map,
            line_type
        )
        # Merge ET placement data
        for size, data in placement_data_et.items():
            if size not in placement_data:
                placement_data[size] = data.copy()
            else:
                # Combine placement IDs from both sources
                existing_ids = set(placement_data[size].get('placement_ids', []))
                new_ids = set(data.get('placement_ids', []))
                placement_data[size]['placement_ids'] = list(existing_ids | new_ids)
                
                # Preserve original_sizes information
                existing_original_sizes = set(placement_data[size].get('original_sizes', []))
                new_original_sizes = set(data.get('original_sizes', []))
                placement_data[size]['original_sizes'] = list(existing_original_sizes | new_original_sizes)
                
                print(f"🔄 Merged ET placements for {size}: {len(new_ids)} new IDs")

    if contains_lang:
        lang_sites = [s for s in site_filter if s not in ['TOI', 'ETIMES', 'ET']]
        print("\nFetching Language placements:")
        placement_data_lang = fetch_placements_ids(
            CREDENTIALS_PATH,
            SHEET_URL,
            PLACEMENT_SHEET_NAME_LANG,
            lang_sites,
            platforms_for_fetch,
            filtered_size_groups,
            richmedia_platform_map,
            line_type
        )
        # Merge Language placement data
        for size, data in placement_data_lang.items():
            if size not in placement_data:
                placement_data[size] = data.copy()
            else:
                # Combine placement IDs from both sources
                existing_ids = set(placement_data[size].get('placement_ids', []))
                new_ids = set(data.get('placement_ids', []))
                placement_data[size]['placement_ids'] = list(existing_ids | new_ids)
                
                # Preserve original_sizes information
                existing_original_sizes = set(placement_data[size].get('original_sizes', []))
                new_original_sizes = set(data.get('original_sizes', []))
                placement_data[size]['original_sizes'] = list(existing_original_sizes | new_original_sizes)
                
                print(f"🔄 Merged Language placements for {size}: {len(new_ids)} new IDs")

    # Safeguard: Ensure original_sizes are preserved from size_groups
    for placement_size, group_data in placement_data.items():
        if placement_size in size_groups:
            expected_original_sizes = size_groups[placement_size].get('original_sizes', [])
            current_original_sizes = group_data.get('original_sizes', [])
            
            # If original_sizes is missing or incorrect, fix it
            if not current_original_sizes or (len(current_original_sizes) == 1 and current_original_sizes[0] == placement_size and expected_original_sizes != [placement_size]):
                placement_data[placement_size]['original_sizes'] = expected_original_sizes.copy()

    print("\nFinal placement data:")
    print(json.dumps(placement_data, indent=2))
    
    # Debug: Show original sizes mapping and data types
    print("\n🔍 Final placement_data debug:")
    print(f"  - placement_data type: {type(placement_data)}")
    print(f"  - placement_data keys: {list(placement_data.keys())}")
    
    for placement_size, data in placement_data.items():
        print(f"🔍 Final - Size: {placement_size}, Data type: {type(data)}")
        if isinstance(data, dict):
            original_sizes = data.get('original_sizes', [placement_size])
            print(f"  - Original sizes: {original_sizes}")
            print(f"  - Placement IDs count: {len(data.get('placement_ids', []))}")
        else:
            print(f"  - ⚠️ WARNING: Data is not a dict: {data}")

    # Get all placement IDs from placement_data
    all_placement_ids = []
    print(f"🔍 Collecting all placement IDs:")
    
    for key, group_info in placement_data.items():
        print(f"  - Processing key: {key}, type: {type(group_info)}")
        if isinstance(group_info, dict):
            placement_ids = group_info.get('placement_ids', [])
            print(f"    - Found {len(placement_ids)} placement IDs")
            all_placement_ids.extend(placement_ids)
        else:
            print(f"    - ⚠️ WARNING: Expected dict but got {type(group_info)}: {group_info}")
    
    all_placement_ids = list(set(all_placement_ids))
    print(f"🔍 Total unique placement IDs collected: {len(all_placement_ids)}")

    # If no placement IDs found, raise an error since inventory targeting is required
    if not all_placement_ids:
        raise ValueError("No placement IDs found. Inventory targeting is required for line item creation.")

    print("Detected creatives:", detected_creatives)
    print("Placement data:", placement_data)

    creative_placeholders = []
    creative_targetings = []
    
    # Create placeholders and targetings only for sizes that have placement IDs
    for base_size, group_info in placement_data.items():
        if group_info.get('placement_ids'):  # Only create if there are placement IDs
            # Get the original sizes for this placement group
            original_sizes = group_info.get('original_sizes', [base_size])
            
            # Create creative placeholders and targetings for each original size
            for original_size in original_sizes:
                # Create a descriptive targeting name for display
                if original_size == "320x100":
                    targeting_display_name = "Mweb_PPD"
                elif original_size == "300x250" and line_type == "richmedia":
                    targeting_display_name = "Mrec_ex"
                elif original_size == "300x600" and line_type == "richmedia":
                    targeting_display_name = "Tower_ex"
                else:
                    targeting_display_name = original_size
                
                creative_placeholders.append({
                    'targetingName': targeting_display_name,
                    'size': {
                        'width': int(original_size.split('x')[0]),
                        'height': int(original_size.split('x')[1])
                    }
                })
                print(f"✅ Added creative placeholder for original size {original_size} with targeting name {targeting_display_name}")
                
                # Create matching targeting for this original size using the placement IDs
                targeting_dict = {
                    'name': targeting_display_name,
                    'targeting': {
                        'inventoryTargeting': {
                            'targetedPlacementIds': group_info['placement_ids'],
                        },
                    }
                }
                creative_targetings.append(targeting_dict)
                print(f"✅ Added creative targeting '{targeting_display_name}' for original size {original_size} using placement IDs from {base_size}")
                print(f"🔍 Creative targeting type: {type(targeting_dict)}, placement_ids type: {type(group_info['placement_ids'])}")
        else:
            print(f"⚠️ Skipping {base_size} - no placement IDs found")

    # Add special targeting for In-Banner Video if needed
    if In_Banner_video and '300x250' not in placement_data:
        creative_placeholders.append({
            'size': {
                'width': 300,
                'height': 250
            }
        })
        print("➕ Added targeting for In-Banner Video 300x250")

    # Add additional sizes for special cases
    if '1260x570' in placement_data and placement_data['1260x570'].get('placement_ids'):
        additional_sizes = ['728x500', '1320x570']
        for size in additional_sizes:
            creative_placeholders.append({
                'size': {
                    'width': int(size.split('x')[0]),
                    'height': int(size.split('x')[1])
                }
            })
        print(f"➕ Added additional sizes {additional_sizes} because 1260x570 was present")

    if '980x200' in placement_data and placement_data['980x200'].get('placement_ids') and '728x90' not in placement_data:
        creative_placeholders.append({
            'size': {
                'width': 728,
                'height': 90
            }
        })
        print("➕ Added additional size 728x90 because 980x200 was present")

    # Add 320x50 override for 320x100 (similar to 728x90 for 980x200)
    # Check if 320x100 exists in any placement data and 320x50 doesn't exist as its own entry
    print(f"🔍 Debugging placement_data.values():")
    print(f"  - placement_data type: {type(placement_data)}")
    print(f"  - placement_data keys: {list(placement_data.keys()) if isinstance(placement_data, dict) else 'Not a dict'}")
    
    has_320x100 = False
    has_explicit_320x50 = False
    
    try:
        for key, data in placement_data.items():
            print(f"  - Key: {key}, Data type: {type(data)}, Data: {data}")
            if isinstance(data, dict):
                original_sizes = data.get('original_sizes', [])
                if '320x100' in original_sizes:
                    has_320x100 = True
                if '320x50' in original_sizes:
                    has_explicit_320x50 = True
            else:
                print(f"  - WARNING: Expected dict but got {type(data)} for key {key}")
    except Exception as e:
        print(f"  - ERROR in placement_data iteration: {e}")
        print(f"  - placement_data content: {placement_data}")
        # Fallback to original logic with error handling
        has_320x100 = any(
            isinstance(data, dict) and '320x100' in data.get('original_sizes', []) 
            for data in placement_data.values()
        )
        has_explicit_320x50 = any(
            isinstance(data, dict) and '320x50' in data.get('original_sizes', []) 
            for data in placement_data.values()
        )
    
    if has_320x100 and not has_explicit_320x50:
        # Add 320x50 creative placeholder (exactly like 728x90 for 980x200)
        # NO targetingName and NO creative targeting - this allows any 320x50 creative to serve
        creative_placeholders.append({
            'size': {
                'width': 320,
                'height': 50
            }
        })
        print("➕ Added additional size 320x50 because 320x100 was present")



    if '600x250' in placement_data and placement_data['600x250'].get('placement_ids'):
        creative_placeholders.append({
            'targetingName': 'Mrec Expando',
            'size': {'width': 300, 'height': 250}
        })
        
        targeting_dict = {
            'name': 'Mrec Expando',
            'targeting': {
                'inventoryTargeting': {
                    'targetedPlacementIds': placement_data['600x250']['placement_ids'],
                },
            }
        }
        creative_targetings.append(targeting_dict)
        print(f"🔍 Added Mrec Expando targeting, type: {type(targeting_dict)}")

    # Check Expresso information for smarter uniqueness handling
    expresso_line_item_found = line_item_data.get('expresso_line_item_found', False)
    expresso_line_item_name = line_item_data.get('expresso_line_item_name', '')
    
    # Clean the line name first to ensure consistency
    cleaned_line_name = line_name.strip() if line_name else ''
    
    # Additional character cleanup and validation
    # Remove any non-printable characters and normalize whitespace
    printable_chars = set(string.printable)
    cleaned_line_name = ''.join(char if char in printable_chars else '' for char in cleaned_line_name)
    cleaned_line_name = ' '.join(cleaned_line_name.split())  # Normalize whitespace
    
    print(f"🔧 Original line name: '{line_name}' (length: {len(line_name)})")
    print(f"🔧 Cleaned line name: '{cleaned_line_name}' (length: {len(cleaned_line_name)})")
    
    # Check for any character differences that might cause API issues
    if line_name != cleaned_line_name:
        print(f"🔧 Character cleanup applied - differences detected:")
        for i, (orig, clean) in enumerate(zip(line_name, cleaned_line_name + ' ' * len(line_name))):
            if orig != clean:
                print(f"   Position {i}: '{orig}' (ord: {ord(orig)}) -> '{clean}' (ord: {ord(clean) if clean else 0})")
                if i > 5:  # Limit output for very long differences
                    print(f"   ... (truncated after showing first 5 differences)")
                    break
    
    # Validate the order and check for potential issues
    print(f"🔍 Performing comprehensive order validation for order {order_id}")
    try:
        order_service = client.GetService('OrderService', version='v202408')
        pql_service = client.GetService('PublisherQueryLanguageService', version='v202408')
        
        # Check order status and details using proper PQL syntax
        statement = {
            'query': f'SELECT Id, Name, Status FROM Orders WHERE Id = {order_id} LIMIT 1'
        }
        print(f"🔍 Executing order validation query: {statement['query']}")
        orders = order_service.getOrdersByStatement(statement)
        
        if orders and len(orders) > 0:
            order = orders[0]
            print(f"✅ Order found - ID: {order['id']}, Name: {order['name']}, Status: {order['status']}")
            
            # Check order status
            if order['status'] not in ['DRAFT', 'PENDING_APPROVAL', 'APPROVED']:
                print(f"⚠️ Warning: Order status is {order['status']}, which might affect line item creation")
            
            # Check for potential uniqueness constraints using proper PQL syntax
            unique_checks = [
                # Basic line item check
                f"SELECT Id, Name FROM LineItems WHERE OrderId = {order_id} LIMIT 100",
                # Time overlap check
                f"SELECT Id, Name, StartDateTime, EndDateTime FROM LineItems WHERE OrderId = {order_id} LIMIT 100",
                # Cost settings check
                f"SELECT Id, Name, CostType, CostPerUnit FROM LineItems WHERE OrderId = {order_id} LIMIT 100"
            ]
            
            print(f"🔍 Checking for existing line items and potential conflicts...")
            for i, check in enumerate(unique_checks, 1):
                try:
                    check_statement = {'query': check}
                    check_response = pql_service.select(check_statement)
                    
                    if hasattr(check_response, 'rows') and check_response.rows:
                        print(f"📊 Check {i} found {len(check_response.rows)} line items:")
                        for row in check_response.rows:
                            values = [val.value for val in row.values]
                            if i == 1:  # Basic line item check
                                print(f"   - Line Item: ID={values[0]}, Name='{values[1]}'")
                            elif i == 2:  # Time overlap check
                                print(f"   - Line Item: ID={values[0]}, Name='{values[1]}', Start={values[2]}, End={values[3]}")
                            elif i == 3:  # Cost settings check
                                print(f"   - Line Item: ID={values[0]}, Name='{values[1]}', CostType={values[2]}, CostPerUnit={values[3]}")
                    else:
                        print(f"✅ Check {i}: No existing line items found")
                        
                except Exception as check_error:
                    print(f"⚠️ Error during check {i}:")
                    print(f"   - Query: {check}")
                    print(f"   - Error: {check_error}")
                    print(f"   - Error type: {type(check_error).__name__}")
            
            # Check for order-level settings that might affect line item creation
            print(f"🔍 Checking order-level settings...")
            settings_query = f"SELECT Id, AllowOverbook, ExternalOrderId FROM Order WHERE Id = {order_id} LIMIT 1"
            try:
                settings_statement = {'query': settings_query}
                print(f"🔍 Executing settings query: {settings_query}")
                settings_response = pql_service.select(settings_statement)
                if hasattr(settings_response, 'rows') and settings_response.rows:
                    settings = settings_response.rows[0]
                    print(f"✅ Order settings found:")
                    print(f"   - Order ID: {settings.values[0].value}")
                    print(f"   - Allow Overbook: {settings.values[1].value}")
                    print(f"   - External Order ID: {settings.values[2].value}")
                else:
                    print("⚠️ No order settings found")
            except Exception as settings_error:
                print(f"⚠️ Error checking order settings:")
                print(f"   - Query: {settings_query}")
                print(f"   - Error: {settings_error}")
                print(f"   - Error type: {type(settings_error).__name__}")
                
        else:
            print(f"❌ Order {order_id} not found or inaccessible!")
            raise ValueError(f"Order {order_id} not found or inaccessible")
            
    except Exception as e:
        print(f"⚠️ Error during order validation: {e}")
        print(f"⚠️ Error type: {type(e).__name__}")
        print(f"⚠️ Continuing with line item creation despite validation errors")
    
    # First check if the line exists in GAM by name
    line_item_service = client.GetService('LineItemService', version='v202408')
    
    # Check for exact name match in GAM
    try:
        gam_statement = {
            'query': f'WHERE name = "{cleaned_line_name}" AND orderId = {order_id}',
            'values': None
        }
        print(f"🔍 Checking if line item exists in GAM with name: {cleaned_line_name}")
        gam_response = line_item_service.getLineItemsByStatement(gam_statement)
        
        if gam_response and gam_response['totalResultSetSize'] > 0:
            existing_gam_line = gam_response['results'][0]
            print(f"✅ Found existing line item in GAM:")
            print(f"   - ID: {existing_gam_line['id']}")
            print(f"   - Name: {existing_gam_line['name']}")
            print(f"   - Order ID: {existing_gam_line['orderId']}")
            print(f"   - Status: {existing_gam_line['status']}")
            raise ValueError(f"Line item already exists in GAM with ID: {existing_gam_line['id']}")
    except Exception as e:
        if 'NOT_FOUND' not in str(e) and 'INVALID_QUERY' not in str(e):
            print(f"⚠️ Error checking GAM for existing line item: {e}")
            print(f"⚠️ Error type: {type(e).__name__}")
    
    # Check if this line exists in Expresso (without _TOI suffix)
    expresso_line_item_id = None
    expresso_line_item_details = None
    base_name = cleaned_line_name.rstrip('_TOI')
    
    if 'LineItem_Details' in line_item_data:
        for item in line_item_data.get('LineItem_Details', []):
            if isinstance(item, dict):  # Ensure item is a dictionary
                item_name = item.get('Line Item Name', '')
                if item_name == base_name:
                    expresso_line_item_id = item.get('Line Item Id')
                    expresso_line_item_details = item
                    print(f"✅ Found matching line item in Expresso:")
                    print(f"   - ID: {expresso_line_item_id}")
                    print(f"   - Name: {item_name}")
                    print(f"   - Targeting: {item.get('Targeting', '')}")
                    break
    
    if expresso_line_item_id:
        print(f"🔍 Checking if Expresso line item {expresso_line_item_id} exists in GAM...")
        try:
            # Try to get the line item directly from GAM by Expresso ID
            statement = {
                'query': f'WHERE id = {expresso_line_item_id}',
                'values': None
            }
            
            try:
                response = line_item_service.getLineItemsByStatement(statement)
                if response and response['totalResultSetSize'] > 0:
                    existing_line = response['results'][0]
                    print(f"⚠️ Line item from Expresso already exists in GAM:")
                    print(f"   - ID: {existing_line['id']}")
                    print(f"   - Name: {existing_line['name']}")
                    print(f"   - Order ID: {existing_line['orderId']}")
                    print(f"   - Status: {existing_line['status']}")
                    raise ValueError(f"Line item already exists in GAM with Expresso ID: {expresso_line_item_id}")
                else:
                    print(f"✅ Line item {expresso_line_item_id} not found in GAM - will create new line item")
                    # Update line_item_data with Expresso details if available
                    if expresso_line_item_details:
                        print("📝 Using targeting details from Expresso:")
                        targeting = expresso_line_item_details.get('Targeting', '')
                        print(f"   - Targeting: {targeting}")
                        # Here you can update line_item_data with more details from Expresso
                        
            except Exception as e:
                if 'NOT_FOUND' not in str(e):
                    print(f"⚠️ Error checking line item in GAM: {e}")
                    print(f"⚠️ Error type: {type(e).__name__}")
                print(f"✅ Will proceed with line item creation")
                
        except Exception as e:
            print(f"⚠️ Error during GAM service call: {e}")
            print(f"⚠️ Error type: {type(e).__name__}")
            print(f"✅ Will proceed with line item creation")
    
    # Check if line name already exists in GAM using the cleaned name
    if check_line_item_name_exists(client, order_id, cleaned_line_name):
        # If it exists, append a unique suffix
        unique_line_name = f"{cleaned_line_name}_C{int(time.time())%1000}"
        print(f"📋 Line name exists, using modified name: {unique_line_name}")
    else:
        # If it doesn't exist, use the cleaned name as-is
        unique_line_name = cleaned_line_name
        print(f"📋 Using cleaned line name as-is: {unique_line_name}")
    
    print(f"🔄 Final line item name: '{unique_line_name}' (length: {len(unique_line_name)})")
    
    # End placement lookup, start line creation timing
    timing_checkpoints['placement_lookup_end'] = time.time()
    timing_checkpoints['line_creation_start'] = time.time()
    
    line_item = {
        'name': unique_line_name,
        'orderId': order_id,
        'targeting': {
            'geoTargeting': {
                'targetedLocations': [{'id': geo_id} for geo_id in geo_targeting_ids] if geo_targeting_ids else []
            },
            'inventoryTargeting': {
                'targetedPlacementIds': all_placement_ids
            }
        },
        'creativePlaceholders': creative_placeholders,
        'creativeTargetings': creative_targetings,
        'endDateTime': structured_end_date,
        'deliveryRateType': 'EVENLY',
        'lineItemType': 'STANDARD',
        'costType': 'CPM',
        'costPerUnit': {
            'currencyCode': currency,
            'microAmount': int(float(cost) * 1_000_000)
        },
        'primaryGoal': {
            'goalType': 'LIFETIME',
            'units': impressions_int
        },
        'allowOverbook': True,
        'skipInventoryCheck': True
    }

    if use_start_date_type:
        line_item['startDateTimeType'] = 'IMMEDIATELY'
    else:
        line_item['startDateTime'] = structured_start_date

    if Fcap_value > 0:
        line_item['frequencyCaps'] = [{
            'maxImpressions': Fcap_value,
            'timeUnit': 'LIFETIME'
        }]

    # Attempt to create the line item with fallback for DUPLICATE_OBJECT errors
    max_attempts = 5  # Increased from 3 to 5 for more fallback options
    attempt = 0
    line_item_id = None
    
    while attempt < max_attempts and line_item_id is None:
        try:
            attempt += 1
            current_line_name = unique_line_name
            
            # If this is a retry attempt, generate a new unique name
            if attempt > 1:
                timestamp_suffix = int(time.time() * 1000) % 100000  # Use milliseconds for uniqueness
                random_suffix = random.randint(10000, 99999)
                
                # Use different naming strategies for different attempts
                if attempt == 2:
                    current_line_name = f"{cleaned_line_name}_R{attempt}_{timestamp_suffix}"
                elif attempt == 3:
                    # More aggressive: truncate if too long and add unique suffix
                    base_name = cleaned_line_name[:90] if len(cleaned_line_name) > 90 else cleaned_line_name
                    current_line_name = f"{base_name}_RETRY_{timestamp_suffix}_{random_suffix}"
                elif attempt == 4:
                    # Ultimate fallback: use UUID for guaranteed uniqueness
                    unique_id = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID
                    base_name = cleaned_line_name[:80] if len(cleaned_line_name) > 80 else cleaned_line_name
                    current_line_name = f"{base_name}_UUID_{unique_id}_{timestamp_suffix}"
                else:
                    # Final attempt: completely different approach with short UUID
                    unique_id = str(uuid.uuid4())[:12].replace('-', '')  # 12 chars, no hyphens
                    # Use expresso ID if available for context
                    expresso_part = f"EXP{expresso_id}" if expresso_id else "LINE"
                    current_line_name = f"{expresso_part}_{unique_id}_{timestamp_suffix}"
                
                print(f"🔄 Retry attempt {attempt}: Using new unique name: '{current_line_name}' (length: {len(current_line_name)})")
                
                # Update the line item with the new name
                line_item['name'] = current_line_name
            
            # Create the line item
            print(f"🚀 Creating line item (attempt {attempt})...")
            created_line_items = line_item_service.createLineItems([line_item])
            line_item_id = created_line_items[0]['id']
            unique_line_name = current_line_name  # Update the final name used
            print(f"✅ Successfully created line item with ID: {line_item_id}")
            
            # End line creation, start creative creation timing
            timing_checkpoints['line_creation_end'] = time.time()
            timing_checkpoints['creative_creation_start'] = time.time()
            
            # Log successful line creation (we'll add creative IDs later)
            logger.log_line_creation_success(
                line_id=line_item_id,
                creative_ids=[],  # Will be populated later
                order_id=str(order_id),
                line_name=unique_line_name,
                session_id=session_id
            )
            
        except Exception as e:
            error_str = str(e)
            print(f"🔍 Detailed error analysis for attempt {attempt}:")
            print(f"   - Error type: {type(e).__name__}")
            print(f"   - Error string: {error_str}")
            
            # Try to extract more details from the error if it's a SOAP fault
            if hasattr(e, 'fault') and hasattr(e.fault, 'detail'):
                print(f"   - SOAP fault details: {e.fault.detail}")
            
            if "DUPLICATE_OBJECT" in error_str and attempt < max_attempts:
                print(f"❌ DUPLICATE_OBJECT error on attempt {attempt}. Details:")
                print(f"   - Name used: '{current_line_name}' (length: {len(current_line_name)} chars)")
                print(f"   - Order ID: {order_id}")
                print(f"   - Will retry with a different name (attempt {attempt + 1}/{max_attempts})")
                print(f"   - Error: {error_str}")
                
                # Add a small delay before retry to avoid potential rate limiting
                time.sleep(0.5)
                continue  # Try again with a new name
            else:
                # Either not a DUPLICATE_OBJECT error, or we've exhausted our attempts
                if "DUPLICATE_OBJECT" in error_str:
                    print(f"❌ DUPLICATE_OBJECT error persists after {max_attempts} attempts:")
                    print(f"   - Final name used: '{current_line_name}' (length: {len(current_line_name)} chars)")
                    print(f"   - Order ID: {order_id}")
                    print(f"   - This suggests a deeper issue with name generation, order status, or API behavior")
                    print(f"   - Recommendation: Check order status in GAM UI and verify no hidden constraints")
                else:
                    print(f"❌ Failed to create line item with different error: {e}")
                
                logger.log_line_creation_error(e, current_line_name, str(order_id), session_id)
                raise

    # Read tags from Excel only if file exists
    tag_dict = read_tag_file()
    
    creative_ids = []
    
    # First, gather all the tags for each base size
    size_tags = {}
    if tag_dict:
        for tag_key in tag_dict.keys():
            base_size = tag_key.split('_')[0].strip()
            if base_size not in size_tags:
                size_tags[base_size] = []
            size_tags[base_size].append(tag_key)
    
    # Process placement_data sizes
    print(f"Processing placement_data sizes: {list(placement_data.keys())}")
    for size_name in placement_data:
        print(f"Processing size_name: {size_name}, has placement_ids: {bool(placement_data[size_name]['placement_ids'])}")
        if placement_data[size_name]['placement_ids']:
            # Get the original sizes that map to this placement size
            original_sizes = placement_data[size_name].get('original_sizes', [size_name])
            print(f"Original sizes for {size_name}: {original_sizes}")
            
            for original_size in original_sizes:
                try:
                    print(f"Creating creative(s) for original size: {original_size} (placement size: {size_name})")
                    
                    # Initialize variables for tag processing
                    use_script_tag = script_tracker
                    use_impression_tag = impression_tracker
                    use_landing_page = landing_page
                    use_template_id = Template_Id
                    
                    # Special handling for 320x100 size - use template ID 12363950
                    if original_size == "320x100":
                        use_template_id = 12363950
                        print(f"Using special template ID: {use_template_id} for size {original_size}")
                    # Special handling for 300x250 richmedia - use template ID 12460223
                    elif original_size == "300x250" and line_type == "richmedia":
                        use_template_id = 12460223
                        print(f"Using 300x250 richmedia template ID: {use_template_id} for size {original_size}")
                    # Special handling for 300x600 richmedia - use template ID 12443458
                    elif original_size == "300x600" and line_type == "richmedia":
                        use_template_id = 12443458
                        print(f"Using 300x600 richmedia template ID: {use_template_id} for size {original_size}")
                    
                    # Special handling for In_Banner_Video
                    elif In_Banner_video and original_size == "300x250":
                        use_template_id = 12344286
                        print(f"Using In-Banner Video template ID: {use_template_id} for size {original_size}")
                        new_creatives = create_custom_template_creatives(
                            client, order_id, line_item_id,
                            destination_url, expresso_id, original_size, use_landing_page,
                            use_impression_tag, use_script_tag, use_template_id, In_Banner_video, line_type
                        )
                        creative_ids.extend(new_creatives)
                        track_creative_creation(original_size, new_creatives)
                        continue
                    
                    # Process tags if available for the original size
                    if tag_dict and original_size in size_tags:
                        # Process each tag for this original_size
                        for tag_key in size_tags[original_size]:
                            tag_info = tag_dict[tag_key]
                            print(f"Processing tag {tag_key} for original size {original_size}")
                            
                            # Reset to defaults for each tag
                            use_script_tag = script_tracker
                            use_impression_tag = impression_tracker
                            use_landing_page = landing_page
                            use_template_id = Template_Id
                            
                            # Special handling for 320x100 size - use template ID 12363950
                            if original_size == "320x100":
                                use_template_id = 12363950
                                print(f"Using special template ID: {use_template_id} for size {original_size}")
                            # Special handling for 300x250 richmedia - use template ID 12460223
                            elif original_size == "300x250" and line_type == "richmedia":
                                use_template_id = 12460223
                                print(f"Using 300x250 richmedia template ID: {use_template_id} for size {original_size}")
                            # Special handling for 300x600 richmedia - use template ID 12443458
                            elif original_size == "300x600" and line_type == "richmedia":
                                use_template_id = 12443458
                                print(f"Using 300x600 richmedia template ID: {use_template_id} for size {original_size}")
                            elif tag_info['type'] == 'impression_click':
                                # For impression/click tag combo, use template 12330939
                                print(f"Using Impression/Click tags from tag.xlsx for size {original_size}")
                                
                                # Process impression tag to extract just the URL from IMG SRC attribute
                                impression_tag_value = tag_info['impression_tag']
                                
                                # Extract URL from IMG SRC tag if it exists
                                if 'IMG SRC=' in impression_tag_value.upper() or 'src=' in impression_tag_value.lower():
                                    url_match = re.search(r'src=["\'](https?://[^"\']+)["\']', impression_tag_value, re.IGNORECASE)
                                    if url_match:
                                        impression_tag_value = url_match.group(1)
                                        # Replace [timestamp] or [CACHEBUSTER] with %%CACHEBUSTER%%
                                        impression_tag_value = impression_tag_value.replace('[timestamp]', '%%CACHEBUSTER%%').replace('[CACHEBUSTER]', '%%CACHEBUSTER%%')
                                        print(f"Extracted URL from impression tag: {impression_tag_value}")
                                
                                use_impression_tag = impression_tag_value
                                use_landing_page = tag_info['click_tag'].replace('[timestamp]', '%%CACHEBUSTER%%').replace('[CACHEBUSTER]', '%%CACHEBUSTER%%')
                                use_template_id = 12330939  # Use the specified template ID
                                print(f"Using template ID: {use_template_id} for impression/click tags")
                            elif tag_info['type'] == 'doubleclick':
                                # For DoubleClick tag
                                print(f"Using DoubleClick tag from tag.xlsx for size {original_size}")
                                use_script_tag = tag_info['js_tag']
                                
                                # Handle <noscript> tags with <a> href, common in Flashtalking tags
                                if '<noscript>' in use_script_tag.lower() and '<a href' in use_script_tag.lower():
                                    print(f"Detected noscript/a href tag for size {original_size}")
                                    href_pattern = r'(<a\s+[^>]*?href=")([^"]*)"'
                                    
                                    # Prepend click macro if not already present
                                    if '%%CLICK_URL_UNESC%%' not in use_script_tag:
                                        replacement = r'\1%%CLICK_URL_UNESC%%\2"'
                                        modified_tag = re.sub(href_pattern, replacement, use_script_tag, flags=re.IGNORECASE)
                                        
                                        if modified_tag != use_script_tag:
                                            use_script_tag = modified_tag
                                            print(f"Added %%CLICK_URL_UNESC%% to href in noscript tag for size {original_size}")
                                        else:
                                            print(f"Warning: Could not add %%CLICK_URL_UNESC%% to href for size {original_size}")
                                    else:
                                        print(f"Click macro already present for size {original_size}")
                                
                                # Ensure the DoubleClick tag has a data-dcm-click-tracker attribute
                                if 'data-dcm-click-tracker' not in use_script_tag:
                                    try:
                                        # First try to add it before class attribute
                                        tag_pattern = r'(<ins|<div)([^>]*?)(\s+class=)'
                                        replacement = r"\1\2 data-dcm-click-tracker='%%CLICK_URL_UNESC%%'\3"
                                        modified_tag = re.sub(tag_pattern, replacement, use_script_tag, flags=re.IGNORECASE)
                                        
                                        # If that didn't work, try adding it after the opening tag
                                        if modified_tag == use_script_tag:
                                            tag_pattern = r'(<ins|<div)(\s)'
                                            replacement = r"\1 data-dcm-click-tracker='%%CLICK_URL_UNESC%%'\2"
                                            modified_tag = re.sub(tag_pattern, replacement, use_script_tag, flags=re.IGNORECASE)
                                        
                                        use_script_tag = modified_tag
                                        print(f"Added data-dcm-click-tracker to DoubleClick tag for size {original_size}")
                                    except Exception as e:
                                        print(f"Warning: Could not add data-dcm-click-tracker attribute: {str(e)}")
                                
                                use_template_id = 12435443
                            else:
                                # For JavaScript tag, use AI template
                                print(f"Using JavaScript tag from tag.xlsx for size {original_size}")
                                use_script_tag = tag_info['js_tag']
                                
                                # Handle <noscript> tags with <a> href, common in Flashtalking tags
                                if '<noscript>' in use_script_tag.lower() and '<a href' in use_script_tag.lower():
                                    print(f"Detected noscript/a href tag for size {original_size}")
                                    href_pattern = r'(<a\s+[^>]*?href=")([^"]*)"'
                                    
                                    # Prepend click macro if not already present
                                    if '%%CLICK_URL_UNESC%%' not in use_script_tag:
                                        replacement = r'\1%%CLICK_URL_UNESC%%\2"'
                                        modified_tag = re.sub(href_pattern, replacement, use_script_tag, flags=re.IGNORECASE)
                                        
                                        if modified_tag != use_script_tag:
                                            use_script_tag = modified_tag
                                            print(f"Added %%CLICK_URL_UNESC%% to href in noscript tag for size {original_size}")
                                        else:
                                            print(f"Warning: Could not add %%CLICK_URL_UNESC%% to href for size {original_size}")
                                    else:
                                        print(f"Click macro already present for size {original_size}")
                                
                                use_template_id = 12435443  # AI template for JavaScript tags
                                print(f"Using AI template ID: {use_template_id} for JavaScript tag")
                            
                            # Check if this is a 2x creative
                            creative_info = detected_creatives.get(original_size, {})
                            is_2x = creative_info.get('is_2x', False)
                            
                            # If it's a 2x creative, use 2x template (override any existing template)
                            if is_2x:
                                use_template_id = 12459443
                                print(f"Using 2x template (12459443) for {original_size} based on image name")
                            
                            # Create the creative and associate it with the line item
                            new_creatives = create_custom_template_creatives(
                                client, order_id, line_item_id,
                                destination_url, expresso_id, original_size, use_landing_page,
                                use_impression_tag, use_script_tag, use_template_id, In_Banner_video, line_type
                            )
                            creative_ids.extend(new_creatives)
                            track_creative_creation(original_size, new_creatives)
                    else:
                        # No tags for this size, create a normal creative
                        creative_path = None
                        if original_size in detected_creatives:
                            creative_path = detected_creatives[original_size].get('image_path', '')
                        # Check if this is a 2x creative
                        creative_info = detected_creatives.get(original_size, {})
                        is_2x = creative_info.get('is_2x', False)
                        
                        # If it's a 2x creative, use 2x template (override any existing template)
                        if is_2x:
                            use_template_id = 12459443
                            print(f"Using 2x template (12459443) for {original_size} based on image name")
                        elif creative_path and creative_path.lower().endswith('.html'):
                            use_template_id = 12435443
                            print(f"Using template ID 12435443 for HTML creative: {creative_path}")
                        new_creatives = create_custom_template_creatives(
                            client, order_id, line_item_id,
                            destination_url, expresso_id, original_size, use_landing_page,
                            use_impression_tag, use_script_tag, use_template_id, In_Banner_video, line_type
                        )
                        creative_ids.extend(new_creatives)
                        track_creative_creation(original_size, new_creatives)
                except Exception as e:
                    print(f"⚠️ Failed to create creatives for original size {original_size}: {e}")

    # Note: 320x50 creative creation is handled later in the consolidated logic

    # Now, process any tag sizes that weren't in placement_data
    if tag_dict:
        print("Checking for additional tag sizes not covered by placement data...")
        # First, get all original sizes that were already processed
        processed_original_sizes = set()
        for group_info in placement_data.values():
            processed_original_sizes.update(group_info.get('original_sizes', []))
        
        print(f"Processed original sizes from placement_data: {processed_original_sizes}")
        print(f"Available tag sizes: {list(size_tags.keys())}")
        
        # Find any tags for sizes that we haven't processed yet
        for tag_size, tag_keys in size_tags.items():
            print(f"Checking tag size: {tag_size}")
            
            # Skip sizes we've already processed
            if tag_size in processed_original_sizes:
                print(f"Tag size {tag_size} already processed, skipping")
                continue
                
            # Skip any non-standard sizes
            if tag_size not in available_presets:
                print(f"Tag size {tag_size} not in available presets, skipping")
                continue
                
            # We have a valid tag size that wasn't in placement_data
            print(f"Creating additional creative(s) for tag size: {tag_size}")
            
            # Process each tag for this tag_size
            for tag_key in tag_keys:
                try:
                    tag_info = tag_dict[tag_key]
                    use_script_tag = script_tracker
                    use_impression_tag = impression_tracker
                    use_landing_page = landing_page
                    use_template_id = Template_Id
                    
                    print(f"Processing tag {tag_key} for additional size {tag_size}")
                    
                    # Special handling for 320x100 size - use template ID 12363950
                    if tag_size == "320x100":
                        use_template_id = 12363950
                        print(f"Using special template ID: {use_template_id} for additional size {tag_size}")
                    # Special handling for 300x250 richmedia - use template ID 12460223
                    elif tag_size == "300x250" and line_type == "richmedia":
                        use_template_id = 12460223
                        print(f"Using 300x250 richmedia template ID: {use_template_id} for additional size {tag_size}")
                    # Special handling for 300x600 richmedia - use template ID 12443458
                    elif tag_size == "300x600" and line_type == "richmedia":
                        use_template_id = 12443458
                        print(f"Using 300x600 richmedia template ID: {use_template_id} for additional size {tag_size}")
                    elif tag_info['type'] == 'impression_click':
                        # For impression/click tag combo
                        impression_tag_value = tag_info['impression_tag']
                        if 'IMG SRC=' in impression_tag_value.upper() or 'src=' in impression_tag_value.lower():
                            url_match = re.search(r'src=["\'](https?://[^"\']+)["\']', impression_tag_value, re.IGNORECASE)
                            if url_match:
                                impression_tag_value = url_match.group(1)
                                impression_tag_value = impression_tag_value.replace('[timestamp]', '%%CACHEBUSTER%%').replace('[CACHEBUSTER]', '%%CACHEBUSTER%%')
                        
                        use_impression_tag = impression_tag_value
                        use_landing_page = tag_info['click_tag'].replace('[timestamp]', '%%CACHEBUSTER%%').replace('[CACHEBUSTER]', '%%CACHEBUSTER%%')
                        use_template_id = 12330939
                    elif tag_info['type'] == 'doubleclick':
                        # For DoubleClick tag
                        print(f"Using DoubleClick tag for additional size {tag_size}")
                        use_script_tag = tag_info['js_tag']
                        
                        # Handle <noscript> tags with <a> href, common in Flashtalking tags
                        if '<noscript>' in use_script_tag.lower() and '<a href' in use_script_tag.lower():
                            print(f"Detected noscript/a href tag for additional size {tag_size}")
                            href_pattern = r'(<a\s+[^>]*?href=")([^"]*)"'
                            
                            # Prepend click macro if not already present
                            if '%%CLICK_URL_UNESC%%' not in use_script_tag:
                                replacement = r'\1%%CLICK_URL_UNESC%%\2"'
                                modified_tag = re.sub(href_pattern, replacement, use_script_tag, flags=re.IGNORECASE)
                                
                                if modified_tag != use_script_tag:
                                    use_script_tag = modified_tag
                                    print(f"Added %%CLICK_URL_UNESC%% to href in noscript tag for additional size {tag_size}")
                                else:
                                    print(f"Warning: Could not add %%CLICK_URL_UNESC%% to href for additional size {tag_size}")
                            else:
                                print(f"Click macro already present for additional size {tag_size}")
                        
                        # Ensure the DoubleClick tag has a data-dcm-click-tracker attribute
                        if 'data-dcm-click-tracker' not in use_script_tag:
                            try:
                                # First try to add it before class attribute
                                tag_pattern = r'(<ins|<div)([^>]*?)(\s+class=)'
                                replacement = r"\1\2 data-dcm-click-tracker='%%CLICK_URL_UNESC%%'\3"
                                modified_tag = re.sub(tag_pattern, replacement, use_script_tag, flags=re.IGNORECASE)
                                
                                # If that didn't work, try adding it after the opening tag
                                if modified_tag == use_script_tag:
                                    tag_pattern = r'(<ins|<div)(\s)'
                                    replacement = r"\1 data-dcm-click-tracker='%%CLICK_URL_UNESC%%'\2"
                                    modified_tag = re.sub(tag_pattern, replacement, use_script_tag, flags=re.IGNORECASE)
                                
                                use_script_tag = modified_tag
                                print(f"Added data-dcm-click-tracker to DoubleClick tag for size {tag_size}")
                            except Exception as e:
                                print(f"Warning: Could not add data-dcm-click-tracker attribute: {str(e)}")
                        
                        use_template_id = 12435443
                    else:
                        # For JavaScript tag
                        use_script_tag = tag_info['js_tag']
                        
                        # Handle <noscript> tags with <a> href, common in Flashtalking tags
                        if '<noscript>' in use_script_tag.lower() and '<a href' in use_script_tag.lower():
                            print(f"Detected noscript/a href tag for additional size {tag_size}")
                            href_pattern = r'(<a\s+[^>]*?href=")([^"]*)"'
                            
                            # Prepend click macro if not already present
                            if '%%CLICK_URL_UNESC%%' not in use_script_tag:
                                replacement = r'\1%%CLICK_URL_UNESC%%\2"'
                                modified_tag = re.sub(href_pattern, replacement, use_script_tag, flags=re.IGNORECASE)
                                
                                if modified_tag != use_script_tag:
                                    use_script_tag = modified_tag
                                    print(f"Added %%CLICK_URL_UNESC%% to href in noscript tag for additional size {tag_size}")
                                else:
                                    print(f"Warning: Could not add %%CLICK_URL_UNESC%% to href for additional size {tag_size}")
                            else:
                                print(f"Click macro already present for additional size {tag_size}")
                        
                        use_template_id = 12435443
                    
                    # Check if this is a 2x creative for additional tag sizes
                    creative_info = detected_creatives.get(tag_size, {})
                    is_2x = creative_info.get('is_2x', False)
                    
                    # If it's a 2x creative, use 2x template (override any existing template)
                    if is_2x:
                        use_template_id = 12459443
                        print(f"Using 2x template (12459443) for additional tag size {tag_size} based on image name")
                    
                    new_creatives = create_custom_template_creatives(
                        client, order_id, line_item_id,
                        destination_url, expresso_id, tag_size, use_landing_page,
                        use_impression_tag, use_script_tag, use_template_id, In_Banner_video, line_type
                    )
                    creative_ids.extend(new_creatives)
                    track_creative_creation(tag_size, new_creatives)
                    print(f"✅ Created additional creative for tag {tag_key} and size {tag_size}")
                except Exception as e:
                    print(f"⚠️ Failed to create additional creative for tag {tag_key} and size {tag_size}: {e}")

    # Create 320x50 creatives when they have their own targeting but aren't in the main placement processing
    # This happens when 320x100 exists and we've added 320x50 as an additional override size
    print(f"🔍 Creative targetings debug:")
    print(f"  - creative_targetings type: {type(creative_targetings)}")
    print(f"  - creative_targetings length: {len(creative_targetings)}")
    for i, targeting in enumerate(creative_targetings):
        print(f"  - Item {i}: type={type(targeting)}, content={targeting}")
    
    has_320x50_targeting = any(
        isinstance(targeting, dict) and targeting.get('name') == '320x50' 
        for targeting in creative_targetings
    )
    processed_320x50 = False
    
    # Check if 320x50 was already processed in the main placement loop
    for size_name in placement_data:
        if placement_data[size_name].get('placement_ids'):
            original_sizes = placement_data[size_name].get('original_sizes', [size_name])
            if '320x50' in original_sizes:
                processed_320x50 = True
                print(f"🔍 320x50 already processed in placement loop for size_name: {size_name}")
                break
    
    # Check if 320x50 creatives were already created
    already_created_320x50 = is_creative_size_already_created('320x50')
    
    print(f"🔍 320x50 Creative Check:")
    print(f"  - has_320x50_targeting: {has_320x50_targeting}")
    print(f"  - processed_320x50: {processed_320x50}")
    print(f"  - already_created_320x50: {already_created_320x50}")
    
    if has_320x50_targeting and not processed_320x50 and not already_created_320x50:
        try:
            print("🔧 Creating 320x50 creative to fulfill the 320x50 targeting (override for 320x100)")
            # Use same settings as would be used for normal creative creation
            use_script_tag = script_tracker
            use_impression_tag = impression_tracker
            use_landing_page = landing_page
            use_template_id = Template_Id or 12330939  # Default to standard template
            
            new_320x50_creatives = create_custom_template_creatives(
                client, order_id, line_item_id,
                destination_url, expresso_id, "320x50", use_landing_page,
                use_impression_tag, use_script_tag, use_template_id, In_Banner_video, line_type
            )
            creative_ids.extend(new_320x50_creatives)
            track_creative_creation('320x50', new_320x50_creatives)
            print(f"✅ Created 320x50 override creative: {new_320x50_creatives}")
        except Exception as e:
            print(f"⚠️ Failed to create 320x50 override creative: {e}")
    elif already_created_320x50:
        print(f"⏭️ Skipping 320x50 creation - already created earlier in the process")

    # Special case for In_Banner_Video: create 300x250 even if not in placement_data
    if In_Banner_video and '300x250' not in placement_data:
        try:
            print("Creating special 300x250 creative for In-Banner Video")
            print(f"In-Banner Video URL: {In_Banner_video}")
            use_template_id = 12344286
            new_creatives = create_custom_template_creatives(
                client, order_id, line_item_id,
                destination_url, expresso_id, "300x250", landing_page,
                impression_tracker, script_tracker, use_template_id, In_Banner_video, line_type
            )
            creative_ids.extend(new_creatives)
            track_creative_creation("300x250", new_creatives)
        except Exception as e:
            print(f"⚠️ Failed to create special In-Banner Video creative: {e}")
                
    # Clear landing_page and impression_tracker after order creation
    line_item_data['landing_page'] = ''
    line_item_data['impression_tracker'] = ''

    # Ensure tracking_tag and banner_video fields are populated
    # Assuming these fields are already populated as needed

    # Set fcap to 0 by default
    line_item_data['fcap'] = 0

    # Set currency to INR
    line_item_data['currency'] = 'INR'

    # End creative creation timing
    timing_checkpoints['creative_creation_end'] = time.time()
    
    # Calculate performance metrics
    end_time = time.time()
    total_time = end_time - start_time
    
    # Calculate individual phase timings
    data_processing_time = (timing_checkpoints['data_processing_end'] - timing_checkpoints['data_processing_start']) if timing_checkpoints['data_processing_end'] else 0
    placement_lookup_time = (timing_checkpoints['placement_lookup_end'] - timing_checkpoints['placement_lookup_start']) if timing_checkpoints['placement_lookup_end'] else 0
    line_creation_time = (timing_checkpoints['line_creation_end'] - timing_checkpoints['line_creation_start']) if timing_checkpoints['line_creation_end'] else 0
    creative_creation_time = (timing_checkpoints['creative_creation_end'] - timing_checkpoints['creative_creation_start']) if timing_checkpoints['creative_creation_end'] else 0
    
    # Log final success with all details
    logger.log_line_creation_success(
        str(line_item_id), 
        [str(cid) for cid in creative_ids] if creative_ids else [], 
        unique_line_name, 
        session_id
    )
    
    # Log performance metrics with detailed timing
    logger.log_performance_metrics({
        'total_time': total_time,
        'data_processing_time': data_processing_time,
        'placement_lookup_time': placement_lookup_time,
        'line_creation_time': line_creation_time,
        'creative_creation_time': creative_creation_time,
        'line_item_id': line_item_id,
        'creative_count': len(creative_ids) if creative_ids else 0,
        'session_id': session_id
    }, session_id)
    
    # Log final performance summary
    print(f"📊 Session Summary:")
    print(f"  - Lines created: 1")
    print(f"  - Creatives created: {len(creative_ids) if creative_ids else 0}")
    print(f"  - Total time: {total_time:.2f}s")
    print(f"  - Success rate: 100.0%")

    return line_item_id, creative_ids

if __name__ == '__main__':
    client = ad_manager.AdManagerClient.LoadFromStorage("googleads1.yaml") 
    order_id = 3741465536
    timestamp = int(time.time())
    line_name = f"27108910DOMEVENTURILROSINALCDMENGNEZSSTDBANNTILTESTARDBANNERPKG209336_{timestamp}"
    line_item_data = {'cpm': 120.0, 'impressions': 1082500, 'site': ['TOI','VK'], 'platforms': ['WEB', 'MWEB', 'AMP'], 'destination_url': 'https://svkm.ac.in/', 'expresso_id': '271089',
                                                                    'landing_page': 'https://svkm.ac.in/', 'Impression_tracker': '', 
                      'Tracking_Tag': '', 'end_date': 13/4/2025, 'fcap': 0, 
                      'geoTargeting': ['Mumbai'], 'Line_label': 'Education', 
                      'Line_name': f'27108910DOMEVENTURTILROSINALLCPMENGNEWSSTDBANNTILSTANDARDBANNERPKG209336_{timestamp}', 
                      'Template_id': '12330939'}
    placement_data= single_line(client, order_id, line_item_data, line_name)
    
    
    # detected_presets, image_files = fetch_images_and_presets(CREATIVES_FOLDER, available_presets, presets_dict)
    # print("✅ Detected Presets:", detected_presets)
    # print("🖼️ Image Files:", image_files)

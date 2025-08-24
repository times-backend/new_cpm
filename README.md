# Google Ad Manager Line Item Creation System - SOP

## Overview
This system automates the creation of line items and creatives in Google Ad Manager (GAM) through a user-friendly web interface. It supports various creative templates, handles multiple file formats, and integrates with Expresso for campaign tracking.

## Prerequisites
1. **Python 3.x Installed**: The project is built using Python, so having Python 3.x installed is essential to run the application.
2. **Required Python Packages**:
   - **dash**: A web application framework for building interactive dashboards. It provides the framework for creating the user interface where users can input data, view results, and interact with the system.
   - **dash-bootstrap-components**: Provides Bootstrap components for styling Dash applications. It offers pre-styled components like buttons, forms, and layouts, making the application visually appealing and responsive.
   - **pandas**: Used to read Excel files, such as the DSD (Data Source Document), allowing for easy extraction and manipulation of data.
   - **google-ads-python**: A client library for interacting with the Google Ads API, used for managing Google Ad Manager resources, such as creating line items and handling ad campaigns programmatically.
   - **gspread**: A Python API for Google Sheets, allowing the application to read and write data to Google Sheets, facilitating data storage and retrieval for campaign tracking and reporting.

3. Required credentials:
   - `googleads1.yaml` - GAM API credentials
   - `credentials.json` - Google Sheets API credentials

## Directory Structure
```
project_root/
├── templates/
│   └── dash_app.py         # Main web application
├── creatives/              # Directory for creative files
├── DSD/                    # DSD related modules
├── config.py              # Configuration and constants
├── single_line.py         # Line item creation logic
├── ros_banner_template_creatives.py  # Creative templates handling
└── README.md              # This documentation
```

## Available Creative Templates

1. **Standard Banner Template (12330939)**
   - Default template for standard banners
   - Requires: Banner image, Landing page URL
   - Supports impression tracking

2. **AI/Script Template (12435443)**
   - For JavaScript/HTML creatives
   - Supports custom scripts and HTML content
   - Used when script code is provided in tag files

3. **No Landing Page Template (12399020)**
   - For creatives without landing pages
   - Only requires banner image and Expresso ID
   - Supports impression tracking

4. **2x Density Template (12459443)**
   - For high-density creatives
   - Indicated by '2x' in filename
   - Supports landing page and impression tracking

5. **Expandable Template (12460223)**
   - For 600x250 expandable creatives
   - Requires both 300x250 and 600x250 images
   - Supports auto-expand functionality

6. **In-Banner Video Template (12344286)**
   - For video banner ads
   - Requires video URL
   - Supports autoplay configuration

## Supported Banner Sizes
- 300x250 (MREC)
- 320x50 (Mobile Banner)
- 125x600 (Skyscraper)
- 300x600 (Half Page)
- 728x90 (Leaderboard)
- 980x200 (Large Leaderboard)
- 320x480 (Mobile Interstitial)
- 1260x570 (Desktop Interstitial)
- 600x250 (Expandable MREC)

## Step-by-Step Usage Guide

### 1. Preparing Creative Files

#### Image Creatives
1. Place creative files in the `creatives/` directory
2. Naming convention:
   - Standard: `size_name.jpg/png/gif` (e.g., `300x250.jpg`)
   - 2x density: Include '2x' in filename (e.g., `300x250_2x.jpg`)
   - No landing page: Include 'nolp' in filename (e.g., `300x250_nolp.jpg`)
   - AI/Custom script: Include 'ai' in filename or use `.html` extension

#### Tag Files
1. Place tag file (Excel format) in root directory
2. Supported names: `tag.xlsx`, `tags.xlsx`
3. Required columns:
   - Dimensions
   - JavaScript Tag or Impression/Click Tag combination

### 2. Using the Web Interface

#### Creating a New Order
1. Select "New Order" in Order Type dropdown
2. Fill in required fields (these must be entered manually for the reasons below):
   - **Email**: Currently using a default email ID; adjustments may be needed.
   - **Expresso ID**: Must be entered manually to fetch all order details.
   - **Industry Label**: Selected manually due to multiple labels with the same name and no standard format in GAM.
   - **Line Item Name**: Different lines are needed in the same order for different concepts, creatives, and goal bifurcation.
   - **Publisher Sites**: Can be removed if CSM uses standard publisher names correctly in DSD.
   - **Platforms**: Can be removed, but some packages require mobile-only campaigns, while DSD may list Mobile+Desktop.
   - **Geo Targeting**: Proper Geo values are not received from the Expresso API, and DSD uses short forms with no fixed format.
   - **Currency**: Not provided by the Expresso API.
   - **Goal (CPM)**: Although received from the Expresso API, packages may contain different concepts and goal bifurcation, requiring manual entry.

#### Using Existing Order
1. Select "Order Already Created"
2. Enter Order ID
3. Fill in remaining fields as above

#### Creative Upload
1. Click "Upload Creative" button
2. Select creative files
3. Verify upload success indicators

#### Form Submission
1. Review all entered information
2. Click "Preview" to verify details
3. Click "Submit" to create line item
4. Monitor success/error messages

### 3. Special Cases

#### No Landing Page Creatives
1. Leave Landing Page URL empty
2. System automatically uses template 12399020
3. No impression tracking will be added

#### In-Banner Video
1. Provide video URL in "In-banner Video URL" field
2. System creates 300x250 creative with video player
3. Autoplay is enabled by default

#### Rich Media Creatives
1. Include "RICHMEDIA" in line item name
2. System uses rich media placement targeting
3. Supports 300x250 and 728x90 sizes

### 4. Troubleshooting

#### Common Issues
1. **Missing Creatives**
   - Verify files in `creatives/` directory
   - Check file naming conventions
   - Ensure supported file formats

2. **Template Selection**
   - Check filename indicators (2x, nolp, ai)
   - Verify tag file format
   - Review line item name for RICHMEDIA

3. **Geo Targeting**
   - Use comma-separated location names
   - Check for valid location names
   - System falls back to all locations if none valid

4. **Upload Errors**
   - Clear existing files using "Clear" button
   - Verify file permissions
   - Check file formats and sizes

## Maintenance

### Regular Tasks
1. Clear creatives folder after successful submissions
2. Monitor log files for errors
3. Update googleads1.yaml when credentials expire
4. Verify Google Sheets API access

### System Updates
1. Update Python packages regularly
2. Monitor GAM API version changes
3. Update template IDs if changed in GAM
4. Maintain placement mappings in Google Sheets

## Support
For technical support or questions:
1. Check error messages in browser console
2. Review application logs
3. Contact system administrator

## Best Practices
1. Always preview before submission
2. Use clear naming conventions for creatives
3. Regularly clear old files
4. Verify all required fields
5. Monitor submission table for status
6. Keep credentials up to date
7. Follow file format guidelines

## Limitations

Currently, we are not using this product for creating CPD bookings due to the following limitations:

1. In CPD, we have to create multiple lines.
2. It runs on the basis of multiple packages, some of which are custom packages.
3. Ad slots are mapped section-wise. 
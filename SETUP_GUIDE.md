# Texas Bill Analyzer - Setup Guide

**Time to deploy:** 20 minutes

---

## Step 1: Deploy Backend (3 minutes)

1. Click the **Deploy to Heroku** button
2. Wait for deployment (~3 minutes)
3. Copy your app URL: `https://your-app-name.herokuapp.com`

---

## Step 2: Create Salesforce Objects (5 minutes)

### Object 1: Legislation__c

**Setup → Object Manager → Create → Custom Object**

**Object Settings:**
- Label: `Legislation`
- Plural Label: `Legislation`
- Object Name: `Legislation`
- Record Name: `Bill Number` (Text)

**Custom Fields:**

| Field Label | API Name | Type | Length/Details |
|-------------|----------|------|----------------|
| Bill Number | Bill_Number__c | Text | 20, External ID, Unique |
| Session | Session__c | Text | 10 |
| Bill PDF URL | Bill_PDF_URL__c | URL | 255 |
| Fiscal Note URL | Fiscal_Note_URL__c | URL | 255 |
| Status | Status__c | Picklist | Draft, Filed, In Committee, Passed, Vetoed |
| Author | Author__c | Text | 255 |
| Bill Description | Bill_Description__c | Long Text Area | 32,768 |

---

### Object 2: Bill_Analysis__c

**Setup → Object Manager → Create → Custom Object**

**Object Settings:**
- Label: `Bill Analysis`
- Plural Label: `Bill Analyses`
- Object Name: `Bill_Analysis`
- Record Name: `Analysis-{000000}` (Auto Number)

**Master-Detail Relationship:**
- Related To: `Legislation__c`
- Field Label: `Legislation`
- Field Name: `Legislation`

**Custom Fields:**

| Field Label | API Name | Type | Length/Details |
|-------------|----------|------|----------------|
| Analysis Date | Analysis_Date__c | Formula (Date/Time) | NOW() |
| Bill Summary | Bill_Summary__c | Long Text Area | 131,072 |
| Fiscal Note Summary | Fiscal_Note_Summary__c | Long Text Area | 131,072 |
| Analysis Summary | Analysis_Summary__c | Long Text Area | 32,768 |
| Total Fiscal Impact | Total_Fiscal_Impact__c | Currency | 16, 2 |

---

## Step 3: Create External Service (5 minutes)

**Setup → External Services → New External Service**

**Basic Info:**
- Service Name: `Texas_Bill_Analyzer`

**Schema Type:** From API Specification

**Upload this JSON** (replace YOUR-APP-NAME with your Heroku app name):
```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "Texas Bill Analyzer",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "https://YOUR-APP-NAME.herokuapp.com"
    }
  ],
  "paths": {
    "/analyzeBillForAgentforce": {
      "post": {
        "operationId": "analyzeBillForAgentforce",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["bill_number"],
                "properties": {
                  "bill_number": {
                    "type": "string"
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Success",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "response": {
                      "type": "string"
                    },
                    "success": {
                      "type": "boolean"
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

**Authentication:**
- Named Credential: Create new
- URL: `https://YOUR-APP-NAME.herokuapp.com`
- Identity Type: `Named Principal`
- Authentication Protocol: `No Authentication`

---

## Step 4: Create Agentforce Action (5 minutes)

**Setup → Agentforce → Actions → New Action**

**Settings:**
- Action Type: `Flow`
- Action Name: `Analyze_Texas_Bill`

**Flow Elements:**

1. **Start** → Input Variable: `billNumber` (Text)
2. **Action** → External Service: `Texas_Bill_Analyzer.analyzeBillForAgentforce`
   - Input: `billNumber` → map to flow variable
3. **Store Output** → Variable: `analysisResponse` (Text)
4. **End** → Output: `analysisResponse`

**Activate the Flow**

---

## Step 5: Add Action to Agent (2 minutes)

**Setup → Agentforce → Your Agent → Topics & Actions**

1. Add Action: `Analyze_Texas_Bill`
2. Instructions:
```
Use this action when users ask about Texas bills.
Ask for the bill number (format: HB 150, SB 2, etc).
Return the full analysis response.
```

**Activate Agent**

---

## Step 6: Test

**Agent Chat:**
- "Analyze HB 150"
- "Tell me about SB 2"
- "What does HB 103 do?"

**Expected:** 
- First request: ~15 seconds (fetching + AI analysis)
- Subsequent requests: ~2 seconds (cached)

---

## Troubleshooting

**404 Error:**
- Check Heroku app URL in External Service schema
- Verify app is running: `heroku ps --app your-app-name`

**Timeout:**
- Normal for first request (15-20 seconds)
- Check Heroku logs: `heroku logs --tail --app your-app-name`

**No Response:**
- Verify External Service action is added to Agent
- Check Named Credential is configured

---

## Monthly Cost

- Heroku Eco Dynos (2x): $10
- Redis Mini: $3
- Heroku Managed Inference: $15-40 (usage-based)

**Total: ~$28-55/month**

---

## Resources

- GitHub: https://github.com/YOUR_USERNAME/texas-bill-analyzer
- Texas Legislature: https://capitol.texas.gov
- Heroku Logs: `heroku logs --tail --app your-app-name`
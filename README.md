# Legilsative Bill Analyzer 🏛️

> AI-powered legislative analysis for Salesforce SEs. Deploy a complete Texas bill analysis system with Agentforce in 20 minutes.

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/RobsPythonThings/texas-bill-analyzer)

---

## What This Does

**For Demos:** Show customers how AI agents can analyze complex government documents, extract fiscal data, and structure information for business use.

**For SEs:** Get a demo-ready demo environment that:
- ✅ Analyzes ANY Texas legislative house bill.
- ✅ Extracts fiscal impacts automatically with Claude AI and performs financial calculations
- ✅ Returns natural language summaries for Agentforce
- ✅ Provides structured data for Salesforce records (and creation of Salesforce records)
- ✅ Caches results for fast repeat queries (45%+ cache hit rate)
- ✅ Handles large bills (500+ pages) with background processing

---

## 🚀 Quick Start (20 Minutes Total)

### Step 1: Deploy Backend (3 minutes)

Click the purple button above ☝️

Heroku will:
1. Create a new app
2. Install Python and dependencies
3. Provision Redis cache ($15/month)
4. Provision Claude AI via Heroku Managed Inference ($0.30 per 1M tokens)
5. Start web and worker dynos ($7/month each)

**Copy your app URL:** `https://your-app-name.herokuapp.com`

---

### Step 2: Setup Salesforce (15 minutes)

#### A. Create Custom Objects (5 min)

**1. Legislation__c (Parent)**
```
API Name: Legislation__c
Fields:
  - Bill_Number__c (Text, 20)
  - Legislative_Session__c (Text, 10)
  - Bill_URL__c (URL, 255)
  - Name (Auto-Number: LG-{00000})
```

**2. Bill_Analysis__c (Child of Legislation)**
```
API Name: Bill_Analysis__c
Relationship: Master-Detail to Legislation__c
Fields:
  - Analysis_Summary__c (Long Text Area, 32000)
  - Fiscal_Note_Summary__c (Long Text Area, 32000)  
  - Total_Fiscal_Impact__c (Currency, 18, 2)
  - Fiscal_Note_URL__c (URL, 255)
  - Analysis_Date__c (Date)
  - Name (Auto-Number: BA-{00000})
```

**That's it! Just 2 objects.**

---

#### B. Configure External Service (3 min)

1. **Setup → External Services → New External Service**
2. **Name:** `TexasBillAnalyzer`
3. **Paste this OpenAPI spec:**

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "Texas Bill Analyzer API",
    "version": "9.2.0"
  },
  "servers": [
    {
      "url": "https://YOUR-APP-NAME.herokuapp.com"
    }
  ],
  "paths": {
    "/analyzeBillForAgentforce": {
      "post": {
        "summary": "Analyze Texas Bill for Agentforce",
        "operationId": "analyzeBillForAgentforce",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "bill_number": {
                    "type": "string",
                    "description": "Bill number (e.g., HB 150, SB 2)"
                  }
                },
                "required": ["bill_number"]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Analysis complete",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "response": {
                      "type": "string",
                      "description": "Formatted natural language response"
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

**Replace `YOUR-APP-NAME` with your actual Heroku app name!**

4. **Save and Test** the connection

---

#### C. Create Agentforce Agent (7 min)

1. **Agentforce Studio → New Agent**
   - Name: `Legislative Analysis Agent`
   - Description: `Analyzes Texas legislative bills`

2. **Add Topic: "Bill Analysis"**
   - **Classification Descriptions:**
     - "User asks to analyze a bill"
     - "User asks about legislation"
     - "User wants bill summary"
     - "User asks for fiscal impact"
   
   - **Instructions:**
     ```
     When the user asks about a Texas bill, extract the bill number and call the analyzeBillForAgentforce action.
     
     Bill numbers follow these patterns:
     - HB 150 (House Bill)
     - SB 2 (Senate Bill)
     - HJ 1 (House Joint Resolution)
     - SJ 5 (Senate Joint Resolution)
     
     After analysis, present the results clearly to the user.
     If they want to save the bill, ask for confirmation.
     ```

3. **Add Action:** `analyzeBillForAgentforce`
   - Select your External Service
   - Map `bill_number` input
   - Action instructions: "Extract bill number from user query and analyze"

4. **Activate Agent**

---

### Step 3: Test It! (2 minutes)

**In Agentforce chat:**
```
"Analyze HB 150"
"What's the fiscal impact of SB 2?"
"Summarize House Bill 216"
```

**Expected response:**
```
📊 BILL ANALYSIS: HB00150

SUMMARY
[Clear 2-3 sentence summary]

💰 FISCAL IMPACT
[3 paragraphs: bottom line, year-by-year breakdown, implementation details]

Five-Year Total: -$X.X billion

📎 View the full fiscal note: [URL]

Would you like to save this bill to Salesforce for tracking?
```

---

## 💰 Cost Breakdown

| Component | Cost | Notes |
|-----------|------|-------|
| **Eco Dynos (2)** | $14/mo | Web + Worker ($7 each) |
| **Redis Mini** | $15/mo | Caching layer |
| **Heroku Inference** | ~$20-50/mo | Usage-based (Claude API) |
| **Total** | **$49-79/mo** | Per SE instance |

**Cost Savings:** Redis caching achieves 45%+ hit rate, reducing Claude API costs significantly.

---


## 🎯 Value Propositions for Customers

### Government / Public Sector
- **Problem:** Staff overwhelmed reading hundreds of bills per session
- **Solution:** AI analyzes bills, extracts fiscal data, flags high-impact legislation
- **ROI:** hours saved annually (example metric from docs)


---

## 🔧 Customization Guide

### Change Legislative Session
```bash
heroku config:set TX_LEGISLATURE_SESSION=90R --app your-app-name
```

### Adjust Cache TTL
Edit `app.py` line ~88:
```python
cache_analysis(bill_number, session, result, ttl=86400)  # 24 hours
```

### Customize Prompts
Edit `generate_bill_summary()` and `extract_fiscal_data_with_claude()` functions in `app.py`

### Add Other States
Fork the repo and modify URL patterns in `try_bill_url_patterns()` for your state's legislature website.

---

## 📚 API Reference

### Endpoints

#### GET /health
Health check with system status
```bash
curl https://your-app.herokuapp.com/health
```

#### POST /analyzeBillForAgentforce
Simple endpoint for Agentforce (returns formatted text)
```bash
curl -X POST https://your-app.herokuapp.com/analyzeBillForAgentforce \
  -H "Content-Type: application/json" \
  -d '{"bill_number": "HB 150"}'
```

**Response:**
```json
{
  "response": "📊 BILL ANALYSIS: HB00150\n\nSUMMARY\n...",
  "success": true
}
```

#### POST /analyzeBill
Full analysis endpoint (returns structured data)
```bash
curl -X POST https://your-app.herokuapp.com/analyzeBill \
  -H "Content-Type: application/json" \
  -d '{"bill_number": "HB 150"}'
```

**Response:**
```json
{
  "bill_number": "HB00150",
  "session": "89R",
  "bill_url": "https://...",
  "fiscal_note_url": "https://...",
  "bill_text": "first 3000 chars...",
  "fiscal_note_summary": "3 paragraph summary...",
  "total_fiscal_impact": -88715399.00,
  "formatted_response": "natural language version...",
  "success": true
}
```

#### GET /cache/stats
View cache performance
```bash
curl https://your-app.herokuapp.com/cache/stats
```

#### POST /cache/invalidate
Clear cache for specific bill
```bash
curl -X POST https://your-app.herokuapp.com/cache/invalidate \
  -H "Content-Type: application/json" \
  -d '{"bill_number": "HB 150"}'
```

---

## 🐛 Troubleshooting

### "Bill not found"
**Cause:** Bill doesn't exist or session is wrong  
**Fix:** Verify bill number on [Texas Legislature](https://capitol.texas.gov) and check session config (89th)

### "Failed to fetch PDF"
**Cause:** Telicon.com is down or URL pattern changed  
**Fix:** Check Heroku logs: `heroku logs --tail --app your-app-name`

### "Cache not working"
**Cause:** Redis addon not provisioned  
**Fix:** Run `heroku addons --app your-app-name` to verify Redis is installed

### "Claude analysis failed"
**Cause:** Heroku Inference credentials missing  
**Fix:** Run `heroku config --app your-app-name` and verify INFERENCE_URL and INFERENCE_KEY are set

### Agent returns raw JSON
**Cause:** Using `/analyzeBill` instead of `/analyzeBillForAgentforce`  
**Fix:** Update External Service to use `/analyzeBillForAgentforce` endpoint

---

## 🎓 Learning Resources

**For SEs:**
- [Agentforce Documentation](https://help.salesforce.com/agentforce)
- [External Services Guide](https://help.salesforce.com/external-services)
- [Heroku Managed Inference](https://devcenter.heroku.com/articles/heroku-inference)

**Architecture Patterns:**
- This app demonstrates: Microservices, Caching, Background Jobs, AI Integration
- Reusable pattern for: Contracts, Reports, Medical Records, any PDF workflow

---

## 🤝 Contributing

Have improvements? Found a bug? Want to add another state?

1. Fork this repo
2. Create a feature branch
3. Submit a pull request

---

## 📝 License

MIT License - use this however you want! Build cool demos and make SEs look good. 🚀

---

## 🙏 Acknowledgments

Built by a Salesforce SE after a pattern of legislative analysis was coming up in customer conversations. Special thanks to:
- Agentforce team for the amazing platform
- Heroku team for Managed Inference
- Claude AI for actually understanding fiscal notes
- Texas Legislature for having (mostly) consistent PDF URLs

---

## 💬 Support

- **Issues:** [GitHub Issues](https://github.com/YOUR_USERNAME/texas-bill-analyzer/issues)
- **SE Slack:** DM Robert Smith (rsmith2@salesforce.com)
- **Heroku Support:** #heroku-ai on Slack and #heroku-support global

---

Click the deploy button at the top! 🎉

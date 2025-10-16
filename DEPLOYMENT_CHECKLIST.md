# Deployment Checklist - Texas Bill Analyzer

Use this to verify everything works before sharing with other SEs.

---

## 📦 Pre-Deployment

### Files Ready
- [ ] `app.json` exists and has correct GitHub URL
- [ ] `README.md` exists with Deploy button
- [ ] `SETUP_GUIDE.md` exists
- [ ] `requirements.txt` is up to date
- [ ] `Procfile` has web + worker processes
- [ ] `runtime.txt` specifies Python version
- [ ] `.gitignore` excludes sensitive files

### GitHub Repository
- [ ] All files pushed to GitHub
- [ ] Repository is public (required for Heroku button)
- [ ] Deploy button URL points to your repo
- [ ] README displays correctly on GitHub

---

## 🚀 Test Deployment (As Fresh SE)

### Deploy Backend
- [ ] Click Deploy to Heroku button
- [ ] Deployment completes without errors (~3 min)
- [ ] App URL works: `https://your-app.herokuapp.com/health`
- [ ] Redis addon provisioned
- [ ] Heroku Managed Inference addon provisioned
- [ ] Both dynos (web + worker) are running

### Test API Directly
```bash
curl -X POST https://your-app.herokuapp.com/analyzeBillForAgentforce \
  -H "Content-Type: application/json" \
  -d '{"bill_number": "HB 150"}'
```

**Expected:** JSON response with analysis (takes ~15 seconds first time)

**Test Again:** Same request should return in ~2 seconds (cache hit)

---

## 📊 Salesforce Setup

### Create Objects
- [ ] Legislation__c created with all fields
- [ ] Bill_Analysis__c created with all fields
- [ ] Master-Detail relationship configured
- [ ] Tab created for Legislation (optional but helpful)

### External Service
- [ ] External Service created
- [ ] OpenAPI schema uploaded successfully
- [ ] Heroku app URL updated in schema
- [ ] Named Credential configured
- [ ] Test connection succeeds

### Agentforce Action
- [ ] Flow created with correct steps
- [ ] External Service action added
- [ ] Input/Output variables mapped
- [ ] Flow activated
- [ ] Action added to Agent

### Agent Configuration
- [ ] Action enabled in Agent
- [ ] Instructions provided to Agent
- [ ] Agent activated

---

## ✅ Testing

### Test 1: Simple Bill (No Fiscal Note)
**Query:** "Analyze HB 179"

**Expected:**
- ✅ Returns bill summary
- ✅ Shows "No fiscal note available"
- ✅ Provides bill URL
- ✅ Completes in ~15 seconds (first time)

---

### Test 2: Bill with Fiscal Note
**Query:** "Analyze HB 103"

**Expected:**
- ✅ Returns bill summary
- ✅ Shows fiscal impact: $-1,525,000
- ✅ Provides fiscal note summary
- ✅ Includes both URLs
- ✅ Completes in ~15 seconds (first time)

---

### Test 3: Cache Hit
**Query:** "Analyze HB 103" (again)

**Expected:**
- ✅ Returns same analysis
- ✅ Completes in ~2 seconds (cached!)

---

### Test 4: Invalid Bill
**Query:** "Analyze HB 99999"

**Expected:** (Fail Gracefully)
- ✅ Returns error message
- ✅ Explains bill not found
- ✅ Doesn't crash

---

### Test 5: Different Bill Types
Try these:
- [ ] House Bill: "HB 150"
- [ ] Senate Bill: "SB 2"
- [ ] House Joint Resolution: "HJ 1"
- [ ] Senate Joint Resolution: "SJ 1"

**Expected:** All should work

---

## 📊 Monitor Performance

### Heroku Dashboard
```bash
heroku logs --tail --app your-app-name
```

**Check for:**
- [ ] No error messages
- [ ] Cache hit logs appearing
- [ ] Worker dyno processing jobs
- [ ] Redis connection stable

### Redis Stats
```bash
heroku redis:info --app your-app-name
```

**Check for:**
- [ ] Memory usage < 80%
- [ ] Cache hit rate > 40%
- [ ] No evicted keys

---

## 🐛 Common Issues & Fixes

### Issue: External Service Fails
**Symptoms:** Agent says "couldn't complete action"

**Check:**
1. Heroku app URL correct in OpenAPI schema?
2. App is running? (check `heroku ps`)
3. Named Credential configured?

**Fix:** Update schema with correct URL, restart app

---

### Issue: Slow First Response
**Symptoms:** Takes 30+ seconds

**Expected:** This is normal for first request!
- Fetching PDF: ~2 seconds
- Claude AI analysis: ~10 seconds
- Fiscal note processing: ~3 seconds

**Second request should be fast (~2s)**

---

### Issue: Cache Not Working
**Symptoms:** Every request is slow

**Check:** Redis addon provisioned?
```bash
heroku addons --app your-app-name
```

**Fix:** Add Redis if missing:
```bash
heroku addons:create heroku-redis:mini
```

---

### Issue: Worker Dyno Not Running
**Symptoms:** Background jobs failing

**Check:**
```bash
heroku ps --app your-app-name
```

**Fix:**
```bash
heroku ps:scale worker=1 --app your-app-name
```

---

## 💰 Cost Verification

**Monthly Costs:**
- Eco Web Dyno: $5
- Eco Worker Dyno: $5
- Redis Mini: $3
- Heroku Managed Inference: $15-40 (usage-based)

**Total: $28-55/month**

**Check Current Usage:**
```bash
heroku addons --app your-app-name
```

---

## 📋 Pre-Share Checklist

Before sharing with other SEs:

- [ ] Deploy button tested personally
- [ ] Fresh Salesforce org tested
- [ ] All test queries work
- [ ] Documentation clear and accurate
- [ ] Screenshots/demo video ready (optional)
- [ ] Heroku cost breakdown documented
- [ ] No hardcoded credentials anywhere

---

## 🎉 Ready to Share!

**Where to Share:**
- SE Slack channel
- Internal wiki/knowledge base
- Demo library
- SE enablement sessions


**Questions or issues?** Open a GitHub issue or ping me in Slack!
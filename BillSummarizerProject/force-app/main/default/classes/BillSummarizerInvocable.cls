public class BillSummarizerInvocable {
    @InvocableMethod(label='Summarize Texas Bill PDF' description='Sends PDF to backend' category='Agentforce')
    public static List<SummaryResponse> summarizeBill(List<SummaryRequest> requests) {
        List<SummaryResponse> responses = new List<SummaryResponse>();
        for (SummaryRequest req : requests) {
            try {
                ContentVersion cv = [SELECT VersionData, Title FROM ContentVersion WHERE Id = :req.contentVersionId LIMIT 1];
                Http http = new Http();
                HttpRequest httpReq = new HttpRequest();
                httpReq.setEndpoint('callout:TexasBillsAPI/summarizeFile');
                httpReq.setMethod('POST');
                httpReq.setTimeout(120000);
                String boundary = 'boundary123';
                String header = '--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="' + cv.Title + '.pdf"\r\nContent-Type: application/pdf\r\n\r\n';
                String footer = '\r\n--' + boundary + '--';
                Blob body = EncodingUtil.base64Decode(EncodingUtil.base64Encode(Blob.valueOf(header)) + EncodingUtil.base64Encode(cv.VersionData) + EncodingUtil.base64Encode(Blob.valueOf(footer)));
                httpReq.setHeader('Content-Type', 'multipart/form-data; boundary=' + boundary);
                httpReq.setBodyAsBlob(body);
                HttpResponse httpRes = http.send(httpReq);
                if (httpRes.getStatusCode() == 200) {
                    Map<String, Object> result = (Map<String, Object>) JSON.deserializeUntyped(httpRes.getBody());
                    SummaryResponse resp = new SummaryResponse();
                    resp.summary = (String) result.get('summary');
                    resp.success = true;
                    responses.add(resp);
                } else {
                    SummaryResponse errorResp = new SummaryResponse();
                    errorResp.success = false;
                    errorResp.errorMessage = 'HTTP ' + httpRes.getStatusCode();
                    responses.add(errorResp);
                }
            } catch (Exception e) {
                SummaryResponse errorResp = new SummaryResponse();
                errorResp.success = false;
                errorResp.errorMessage = e.getMessage();
                responses.add(errorResp);
            }
        }
        return responses;
    }
    public class SummaryRequest { @InvocableVariable(required=true) public String contentVersionId; }
    public class SummaryResponse { @InvocableVariable public String summary; @InvocableVariable public Boolean success; @InvocableVariable public String errorMessage; }
}
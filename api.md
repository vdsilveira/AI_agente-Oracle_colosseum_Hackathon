Receive a batch of video URLs from the AI Agent, analyze them concurrently, and return normalized results.

Parameters
Cancel
Reset
No parameters

Request body

application/json
Edit Value
Schema
{
  "job_id": "teste_novo_schema",
  "deep_analysis": false,
  "tasks": [
    {
      "user_handle": "joao",
      "videos": [
        {
          "url": "https://www.youtube.com/watch?v=EgpwRtPobOQ",
          "platform": "youtube"
        }
      ]
    }
  ]
}
Execute
Clear
Responses
Curl

curl -X 'POST' \
  'https://backend-views-solana.onrender.com/api/v1/analyze' \
  -H 'accept: application/json' \
  -H 'X-API-Key: your_jwt_token_here' \
  -H 'Content-Type: application/json' \
  -d '{
  "job_id": "teste_novo_schema",
  "deep_analysis": false,
  "tasks": [
    {
      "user_handle": "joao",
      "videos": [
        {
          "url": "https://www.youtube.com/watch?v=EgpwRtPobOQ",
          "platform": "youtube"
        }
      ]
    }
  ]
}'
Request URL
https://backend-views-solana.onrender.com/api/v1/analyze
Server response
Code	Details
200	
Response body
Download
{
  "status": "success",
  "job_id": "teste_novo_schema",
  "summary": [
    {
      "user_handle": "joao",
      "platforms": [
        "youtube"
      ],
      "total_videos_analyzed": 1,
      "videos": [
        {
          "platform": "youtube",
          "video_id": "EgpwRtPobOQ",
          "title": "Casamento falido, amante casada e uma filha no meio… caos total",
          "user_handle": "joao",
          "youtube_channel": "Rotina do Trezoitão",
          "metrics": {
            "views": 27870,
            "likes": 3722,
            "comments": 267
          },
          "comment_sample": [],
          "normalized_at": "2026-04-24T19:36:02.846334Z"
        }
      ]
    }
  ]
}
Response headers
 alt-svc: h3=":443"; ma=86400 
 cf-cache-status: DYNAMIC 
 cf-ray: 9f178df68c9ac4ce-GRU 
 content-encoding: br 
 content-length: 324 
 content-type: application/json 
 date: Fri,24 Apr 2026 19:36:02 GMT 
 priority: u=1,i 
 rndr-id: a046882b-d121-4ffc 
 server: cloudflare 
 server-timing: cfExtPri 
 vary: Accept-Encoding 
 x-render-origin-server: uvicorn 
Responses
Code	Description	Links
200	
Successful Response

Media type

application/json
Controls Accept header.
Example Value
Schema
{
  "status": "string",
  "job_id": "string",
  "summary": [
    {
      "user_handle": "string",
      "platforms": [
        "string"
      ],
      "total_videos_analyzed": 0,
      "videos": [
        {
          "platform": "string",
          "video_id": "string",
          "title": "",
          "user_handle": "",
          "youtube_channel": "string",
          "metrics": {
            "views": 0,
            "likes": 0,
            "comments": 0
          },
          "comment_sample": [
            "string"
          ],
          "normalized_at": "2026-04-24T19:36:00.745Z"
        }
      ]
    }
  ]
}
No links
422	
Validation Error

Media type

application/json
Example Value
Schema
{
  "detail": [
    {
      "loc": [
        "string",
        0
      ],
      "msg": "string",
      "type": "string",
      "input": "string",
      "ctx": {}
    }
  ]
}
No links
infra




Schemas
AnalysisBatchRequestCollapse allobject
Batch request sent by the AI Agent.

Attributes: job_id: Unique identifier for this analysis job. deep_analysis: When True, fetch comment samples per video. tasks: List of task groups, each containing a user handle and their associated video URLs and platforms.

job_idstring
deep_analysisExpand allboolean
tasksExpand allarray<object>
AnalysisBatchResponseCollapse allobject
Top-level response returned to the AI Agent. Results are grouped by user_handle in the summary field.

statusstring
job_idstring
summaryExpand allarray<object>
HTTPValidationErrorCollapse allobject
detailExpand allarray<object>
MetricsCollapse allobject
Normalized engagement metrics for a single video.

viewsinteger
likesinteger
commentsinteger
UserSummaryCollapse allobject
Aggregated results for a single content creator.

Groups all analyzed videos under one user_handle, listing the platforms involved and the total count of videos analyzed.

user_handlestring
platformsExpand allarray<string>
total_videos_analyzedinteger
videosExpand allarray<object>
UserTaskGroupCollapse allobject
A group of video tasks belonging to a specific user.

user_handlestring
videosExpand allarray<object>
ValidationErrorCollapse allobject
locExpand allarray<(string | integer)>
msgstring
typestring
inputany
ctxobject
VideoResultCollapse allobject
Result for a single analyzed video, normalized across platforms.

Attributes: platform: Source platform (e.g., "youtube", "instagram"). video_id: Platform-specific video identifier. title: Video title. user_handle: Content creator handle this video belongs to. youtube_channel: The visual channel name if available (e.g., from YouTube). metrics: Engagement metrics. comment_sample: Sample comments when deep_analysis is enabled. normalized_at: Timestamp when the data was normalized.

platformstring
video_idstring
titleExpand allstring
user_handleExpand allstring
youtube_channelExpand all(string | null)
metricsExpand allobject
comment_sampleExpand allarray<string>
normalized_atstringdate-time
VideoTaskCollapse allobject
A single target video URL with its platform.

urlstringuri[1, 2083] characters
platformstring
Error path test (T05): station API stopped (port 8010 closed), llama-server and n8n running.
`curl -X POST http://127.0.0.1:5678/webhook/hiresignal -F cv=@<P35 cv> -F job_text=<J4.txt` -> `HTTP 500 {"message":"Error in workflow"}` after 5.5 s
(HTTP /reader: 2 tries, 5 s apart). n8n execution 11 (HireSignal v1) = error; execution 12 (HireSignal errors) = success.
`n8n_errors_log.txt` = copy of `eval/logs/n8n_errors.log` (git-ignored as *.log) with the line written by the error workflow.
First attempt (execution 10): n8n log "Workflow "HsV1Errors000001" is not active and cannot be executed" -> the error
workflow must be published in n8n 2.x. After `publish:workflow --id=HsV1Errors000001` + restart: line written.
The station API was restarted afterwards (`start_stack.ps1`).

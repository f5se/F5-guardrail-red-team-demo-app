1. Download the compaign run raw json from system, change the `token` and the `run-id` to yours:

   ```shell
   python get-campaign-rerport-full.py \
     --base-url https://us1.calypsoai.app \
     --token "Your-token" \
     --run-id 019fdf9697b-fe67-709f-9088-af7bdfsf2fe1a \ 
     --output ./
   
   Saved: ./campaign-run-019fdf9697b-fe67-709f-9088-af7bdfsf2fe1a-20260311T011840Z.json
   ```

   

2. Generate the report:

   ```shell
   python campaign_run_analyzer_v2.py   \
     --input ./campaign-run-019fdf9697b-fe67-709f-9088-af7bdfsf2fe1a-20260311T011840Z.json \
     --output ./campaign_run_report_example.html \
     --title "F5 AI Red Team Campaign test Report"
   OK: report written to ./campaign_run_report_example.html
   ```

   
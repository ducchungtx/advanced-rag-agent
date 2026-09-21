@echo off
cd /d "c:\Users\lulx1\Desktop\Projects\AI"
set PYTHONIOENCODING=utf-8
"c:\Users\lulx1\Desktop\Projects\AI\rag_env\Scripts\python.exe" -u "c:\Users\lulx1\Desktop\Projects\AI\scripts\run_ingest.py" >> "c:\Users\lulx1\Desktop\Projects\AI\data\ingest.log" 2>> "c:\Users\lulx1\Desktop\Projects\AI\data\ingest.err.log"

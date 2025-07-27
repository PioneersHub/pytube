#!/bin/bash

echo "🚀 Starting n8n server..."
echo ""
echo "n8n will be available at: http://localhost:5678"
echo ""
echo "📝 First time setup:"
echo "1. Create an account when prompted"
echo "2. Import the workflow from: n8n_workflow_template.json"
echo "3. Configure credentials as needed"
echo ""
echo "Press Ctrl+C to stop n8n"
echo ""

# Start n8n
n8n start
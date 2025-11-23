/**
 * Lambda@Edge function for CloudFront Basic Authentication
 *
 * Deploy this to Lambda@Edge (us-east-1 region only!)
 * Attach to CloudFront distribution as Viewer Request trigger
 *
 * Usage:
 * 1. Create Lambda in us-east-1 region
 * 2. Publish version
 * 3. Attach to CloudFront → Behaviors → Viewer Request
 * 4. Deploy CloudFront changes (takes ~15 min)
 *
 * Login credentials:
 * - Username: admin
 * - Password: CHANGE_THIS_PASSWORD
 */

'use strict';

exports.handler = (event, context, callback) => {

    // Get request and headers
    const request = event.Records[0].cf.request;
    const headers = request.headers;

    // Configure authentication
    const authUser = 'admin';
    const authPass = 'CHANGE_THIS_PASSWORD'; // ⚠️ CHANGE THIS!

    // Build Basic Auth string
    const authString = 'Basic ' + Buffer.from(authUser + ':' + authPass).toString('base64');

    // Check if Authorization header is present and correct
    if (typeof headers.authorization !== 'undefined' &&
        headers.authorization[0].value === authString) {
        // Authentication successful - allow request
        callback(null, request);
        return;
    }

    // Authentication failed - return 401 with WWW-Authenticate header
    const response = {
        status: '401',
        statusDescription: 'Unauthorized',
        headers: {
            'www-authenticate': [{
                key: 'WWW-Authenticate',
                value: 'Basic realm="Newsletter Admin"'
            }],
            'content-type': [{
                key: 'Content-Type',
                value: 'text/html'
            }]
        },
        body: `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Authentication Required</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        min-height: 100vh;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        margin: 0;
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 12px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 {
                        color: #e535ab;
                        margin-bottom: 20px;
                    }
                    p {
                        color: #666;
                        line-height: 1.6;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🔒 Authentication Required</h1>
                    <p>
                        You need to login to access the Newsletter Admin.
                    </p>
                    <p>
                        <small>Yallabalagan Newsletter System</small>
                    </p>
                </div>
            </body>
            </html>
        `
    };

    callback(null, response);
};

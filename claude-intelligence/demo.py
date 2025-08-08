#!/usr/bin/env python3
"""
Demo script for Claude Intelligence
Shows the core features in action
"""

import os
import tempfile
import shutil
from pathlib import Path
from mcp_server import ClaudeIntelligence
import asyncio


def create_demo_project():
    """Create a demo React project structure"""
    # Create package.json
    with open('package.json', 'w') as f:
        f.write("""{
  "name": "demo-app",
  "version": "1.0.0",
  "dependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0",
    "express": "^4.18.0"
  }
}""")
    
    # Create source files
    Path('src').mkdir(exist_ok=True)
    
    with open('src/PaymentProcessor.js', 'w') as f:
        f.write("""
// Payment processing module
import Stripe from 'stripe';

export function processPayment(amount, currency) {
    // Process payment through Stripe
    return stripe.charges.create({
        amount: amount,
        currency: currency
    });
}

export function refundPayment(chargeId) {
    // Handle refunds
    return stripe.refunds.create({charge: chargeId});
}
""")
    
    with open('src/AuthService.js', 'w') as f:
        f.write("""
// Authentication service
import jwt from 'jsonwebtoken';

export function login(username, password) {
    // Authenticate user
    if (validateCredentials(username, password)) {
        return generateToken(username);
    }
    throw new Error('Invalid credentials');
}

function generateToken(username) {
    return jwt.sign({username}, process.env.JWT_SECRET);
}
""")
    
    with open('src/UserDashboard.jsx', 'w') as f:
        f.write("""
// User dashboard component
import React from 'react';
import { PaymentHistory } from './PaymentHistory';

export function UserDashboard({user}) {
    return (
        <div className="dashboard">
            <h1>Welcome {user.name}</h1>
            <PaymentHistory userId={user.id} />
        </div>
    );
}
""")


async def main():
    print("🧠 Claude Intelligence Demo")
    print("=" * 50)
    
    # Create temp directory for demo
    demo_dir = tempfile.mkdtemp(prefix='claude-demo-')
    original_dir = os.getcwd()
    os.chdir(demo_dir)
    
    try:
        # Create demo project
        print("\n📁 Creating demo React project...")
        create_demo_project()
        
        # Initialize Claude Intelligence
        print("\n🚀 Starting Claude Intelligence...")
        server = ClaudeIntelligence()
        
        # Index the project
        print("\n📊 Indexing project files...")
        for update in server.index_progressive():
            print(f"  {update}")
        
        # Detect tech stack
        print("\n🔍 Detecting technology stack...")
        project_info = await server.understand_project()
        print(f"  Stack: {', '.join(project_info['stack'])}")
        print(f"  Summary: {project_info['summary']}")
        
        # Demo searches
        print("\n🔎 Demonstrating semantic search...")
        
        searches = [
            ("payment", "Finding payment-related files"),
            ("authentication", "Finding auth-related files"),
            ("user", "Finding user-related files"),
            ("stripe", "Finding Stripe integration")
        ]
        
        for query, description in searches:
            print(f"\n  {description}...")
            print(f"  Query: '{query}'")
            results = await server.find_files(query, k=3)
            
            if results:
                for result in results:
                    print(f"    ✓ {result['path']} (score: {result['score']:.2f})")
                    if result.get('excerpt'):
                        excerpt = result['excerpt'][:60] + '...' if len(result['excerpt']) > 60 else result['excerpt']
                        print(f"      {excerpt}")
            else:
                print(f"    No results found")
        
        # Show storage size
        print("\n💾 Storage usage:")
        db_size = Path('.claude-memory.db').stat().st_size / 1024
        print(f"  Database size: {db_size:.1f} KB")
        
    finally:
        # Cleanup
        os.chdir(original_dir)
        shutil.rmtree(demo_dir)
        print(f"\n✅ Demo complete! (cleaned up {demo_dir})")


if __name__ == '__main__':
    asyncio.run(main())
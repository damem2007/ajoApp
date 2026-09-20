"""Never let local environment credentials connect regression tests to real data."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['AJO_PLATFORM_DATABASE_URL'] = 'sqlite:///:memory:'

os.environ['AJO_DEMO_MODE'] = 'false'
os.environ['AJO_FRONTEND_ORIGIN'] = 'http://frontend.test'
os.environ['CORS_ALLOWED_ORIGINS'] = 'http://frontend.test'

os.environ['AJO_PROVIDER_MODE'] = 'unconfigured'

os.environ['AJO_DATABASE_RESILIENCE'] = 'false'

for kind in ['PAYMENTS','IDENTITY','NOTIFICATIONS']:
    os.environ['AJO_'+kind+'_PROVIDER']='unconfigured'

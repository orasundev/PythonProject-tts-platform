from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://neondb_owner:npg_0vQrHguVwS9j@ep-red-tooth-aogi7dr4-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        print(result.fetchone())
        print("Connection Successful")
except Exception as e:
    print("Error in Connection")
    print(e)






#
# import sys
# print("Interpreter:", sys.executable)
# from sqlalchemy import create_engine, text
#
# # DATABASE_URL = "postgresql://neondb_owner:npg_UdgDZb3n2jxf@ep-muddy-scene-a4nync60-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
# DATABASE_URL="postgresql+asyncpg://neondb_owner:npg_0vQrHguVwS9j@ep-red-tooth-aogi7dr4-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?ssl=require&channel_binding=require"
#
# engine = create_engine(DATABASE_URL)
#
# with engine.connect() as conn:
#     result = conn.execute(text("SELECT 1"))
#     print("Connection successful! Result:", result.fetchone())
#
#
# ----------------------------
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker, declarative_base
#
# # Replace with your Neon connection string
# DATABASE_URL = (
#     "postgresql+asyncpg://neondb_owner:npg_0vQrHguVwS9j@ep-red-tooth-aogi7dr4-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?ssl=require&channel_binding=require"
# )
#
# # Create Engine
# engine = create_engine(
#     DATABASE_URL,
#     echo=True
# )
#
# # Create Session
# SessionLocal = sessionmaker(
#     autocommit=False,
#     autoflush=False,
#     bind=engine
# )
#
# # Base Class
# Base = declarative_base()
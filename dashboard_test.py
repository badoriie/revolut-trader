"""Simple test to verify Streamlit works"""
import streamlit as st

st.title("✅ Dashboard Test")
st.success("If you see this, Streamlit is working!")

st.write("Python version:", st.__version__)

# Test data
st.metric("Test Metric", "100", delta="10")

# Test chart
import pandas as pd
df = pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 30]})
st.line_chart(df.set_index("x"))

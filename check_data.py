import pandas as pd
df = pd.read_excel('埋点数据.xlsx', sheet_name='埋点数据')

print('event_type唯一值:')
print(df['event_type'].value_counts().to_string())

print('\nintent唯一值:')
print(df['intent'].value_counts().to_string())

print('\nrisk_type唯一值:')
print(df['risk_type'].value_counts().to_string())

print('\ntransfer_json非空数:', df['transfer_json'].notna().sum())

kw = df['payload_json'].dropna()
print('payload_json含knowledge_search:', sum(1 for x in kw if 'knowledge_search' in str(x)))
print('payload_json含answer_generate:', sum(1 for x in kw if 'answer_generate' in str(x)))
print('payload_json含has_result.*true:', sum(1 for x in kw if 'has_result' in str(x)))

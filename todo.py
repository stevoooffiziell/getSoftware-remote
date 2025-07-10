# TODO:
#   bug fixing:
#       simplify following error
#           Fehler beim Einfügen in Test-DB: ('42000', '[42000] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Zeichenfolgen- oder Binärdaten werden in Tabelle "sw_inst.dbo.table_prod", Spalte "name" abgeschnitten. Abgeschnittener Wert: PTV Europe City Map Premium 2022.1H (C:\\Program Files (x86)\\PTVGROUP\\maps\\EuropePremium202. (2628) (SQLExecDirectW); [42000] [Microsoft][ODBC Driver 17 for SQL Server][SQL Server]Die Anweisung wurde beendet. (3621)')
#       dynamic language switch (change all logs / console outputs to english for now, until dynamic language switch has been implemented
#   future changes:
#       make tables dynamic -> config.ini
#       MORE EXCEPTIONHANDLING!
#       make the code more efficient
#       documentation, maybe even a readme.md file
#           - How to install SQL Driver
#           - How to identify them
#       clean up unused imports (done)
#   long-term future changes:
#       make even more databases compatible not only MSSQL
#           - MSSQL (done)
#           - mysql (not implemented)
#           - Oracle (not implemented)
#           - PostgreSQL (not implemented)

# Would a GUI - at least for windows - make sense?
# I guess I'd rather go with a website, which is configurable and the process can be activated manually
# Or should it just be implemented as a service?
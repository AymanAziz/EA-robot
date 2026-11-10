#property script_show_inputs

input string OutputFile = "goldnix_account_snapshot.csv";

void OnStart()
{
   for(int attempt = 0; attempt < 120; ++attempt)
   {
      if(TerminalInfoInteger(TERMINAL_CONNECTED)
         && AccountInfoInteger(ACCOUNT_LOGIN) > 0
         && AccountInfoString(ACCOUNT_SERVER) != "")
         break;
      Sleep(500);
   }
   if(!TerminalInfoInteger(TERMINAL_CONNECTED)
      || AccountInfoInteger(ACCOUNT_LOGIN) <= 0)
   {
      Print("Account snapshot aborted: terminal did not authorize within 60 seconds");
      return;
   }
   Sleep(1000);

   const int file = FileOpen(OutputFile, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(file == INVALID_HANDLE)
   {
      PrintFormat("Cannot open %s: %d", OutputFile, GetLastError());
      return;
   }

   FileWrite(file,
             "terminal_connected",
             "account_server",
             "account_name",
             "login_suffix",
             "currency",
             "trade_mode",
             "trade_allowed",
             "balance",
             "credit",
             "profit",
             "equity",
             "margin_free",
             "margin_mode");
   FileWrite(file,
             IntegerToString((int)TerminalInfoInteger(TERMINAL_CONNECTED)),
             AccountInfoString(ACCOUNT_SERVER),
             AccountInfoString(ACCOUNT_NAME),
             IntegerToString((int)(AccountInfoInteger(ACCOUNT_LOGIN) % 10000)),
             AccountInfoString(ACCOUNT_CURRENCY),
             IntegerToString((int)AccountInfoInteger(ACCOUNT_TRADE_MODE)),
             IntegerToString((int)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)),
             DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
             DoubleToString(AccountInfoDouble(ACCOUNT_CREDIT), 2),
             DoubleToString(AccountInfoDouble(ACCOUNT_PROFIT), 2),
             DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2),
             DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2),
             IntegerToString((int)AccountInfoInteger(ACCOUNT_MARGIN_MODE)));
   FileClose(file);
   PrintFormat("Account snapshot written to Common/Files/%s", OutputFile);
}

#ifndef GOLDNIX_PROFIT_MANAGER
#define GOLDNIX_PROFIT_MANAGER
#include <Trade/Trade.mqh>
#include "ProfitJournal.mqh"

// Production adapter also exercised by the tester-only integration harness.
class ProfitManager
{
private:
   ProfitRecord record;
   bool loaded;
   string path;
   datetime last_request;
public:
   string status;
   int modifications,close_requests;
   ProfitManager() {loaded=false;last_request=0;status="waiting_for_position";modifications=0;close_requests=0;}
   double Peak() {return loaded ? record.direction*(record.peak-record.entry) : 0;}
   double AcceptedSL() {return loaded ? record.accepted_sl : 0;}
   bool Observe(const ulong ticket,const long owner,const long magic,const string root)
   {
      if(!PositionSelectByTicket(ticket)) {status="position_gone";return true;}
      double entry=PositionGetDouble(POSITION_PRICE_OPEN),sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
      double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
      ulong id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
      int direction=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1 : -1;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=magic || tick<=0 || owner<=0 || magic<=0 || id==0)
      {status="protection_identity_invalid";return false;}
      if(!loaded || record.magic!=magic || record.position!=id)
      {
         loaded=false;path=root+"\\protection_"+(string)magic+".csv";last_request=0;
         if(FileIsExist(path,0))
         {
            if(!ReadProfit(path,owner,magic,record)) {status="protection_journal_invalid";return false;}
         }
         else
         {
            // Never reconstruct an original risk unit from an already profitable stop.
            if(direction*(entry-sl)<=0) {status="protection_journal_missing";return false;}
            record.owner=owner;record.magic=magic;record.position=id;record.direction=direction;
            record.entry=entry;record.initial_sl=sl;record.tp=tp;record.peak=entry;record.accepted_sl=sl;record.close_requested=false;
            if(!SaveProfit(path,record)) {status="protection_journal_write_failed";return false;}
         }
         loaded=true;
      }
      if(record.owner!=owner || record.magic!=magic || record.position!=id || record.direction!=direction ||
         MathAbs(entry-record.entry)>tick*.01 || !ProfitStopAccepted(direction,record.initial_sl,record.accepted_sl,sl,record.tp,tp,tick))
      {status="protection_changed_or_weakened";return false;}
      // Handles a crash after broker success and before local confirmation was persisted.
      if(direction*(sl-record.accepted_sl)>tick*.01)
      {
         record.accepted_sl=sl;
         if(!SaveProfit(path,record)) {status="protection_journal_write_failed";return false;}
      }
      return true;
   }
   int Manage(CTrade &broker,const ulong ticket,const long owner,const long magic,const string root,
      const datetime now,const MqlTick &quote,const bool fresh,const bool permitted)
   {
      if(!Observe(ticket,owner,magic,root)) return -1;
      if(!PositionSelectByTicket(ticket)) {status="position_gone";return 0;}
      if(!fresh || quote.bid<=0 || quote.ask<quote.bid) {status="protection_wait_fresh_quote";return 0;}
      if(!permitted) {status="protection_wait_permission";return 0;}
      double entry_charges=0;
      if(!HistorySelectByPosition(record.position)) {status="protection_wait_cost_history";return 0;}
      for(int j=0;j<HistoryDealsTotal();j++)
      {
         ulong deal=HistoryDealGetTicket(j);long side=0;double commission=0,fee=0;
         if(deal==0 || !HistoryDealGetInteger(deal,DEAL_ENTRY,side) || !HistoryDealGetDouble(deal,DEAL_COMMISSION,commission) || !HistoryDealGetDouble(deal,DEAL_FEE,fee))
         {status="protection_wait_cost_history";return 0;}
         if(side==DEAL_ENTRY_IN) entry_charges+=commission+fee;
      }
      if(!PositionSelectByTicket(ticket)) {status="position_gone";return 0;}
      ENUM_ORDER_TYPE type=record.direction>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      double unit_profit=0;
      if(!OrderCalcProfit(type,_Symbol,PositionGetDouble(POSITION_VOLUME),record.entry,record.entry+record.direction,unit_profit) ||
         !MathIsValidNumber(unit_profit) || unit_profit<=0) {status="protection_wait_cost_conversion";return 0;}
      string currency=AccountInfoString(ACCOUNT_CURRENCY);
      if(currency!="USC" && currency!="USD") {status="protection_currency_invalid";return -1;}
      double reserve=currency=="USC" ? .20 : .002; // USD accepted only by the tester harness; production identity requires USC.
      double cost_price=(2*MathMax(0,-entry_charges)+MathMax(0,-PositionGetDouble(POSITION_SWAP))+reserve)/unit_profit;
      double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
      long stops=0,freeze=0;
      if(!SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL,stops) || !SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL,freeze) || point<=0)
      {status="protection_wait_broker_limits";return 0;}
      double desired=0,peak=0,actual_sl=PositionGetDouble(POSITION_SL);
      int action=ProfitPlan(record.direction,record.entry,record.initial_sl,actual_sl,record.tp,quote.bid,quote.ask,record.peak,tick,
         stops*point,freeze*point,cost_price,desired,peak);
      if(action==PROFIT_INVALID) {status="protection_inputs_invalid";return -1;}
      bool changed=peak!=record.peak;record.peak=peak;
      if(action==PROFIT_EXIT && !record.close_requested) {record.close_requested=true;changed=true;}
      if(changed && !SaveProfit(path,record)) {status="protection_journal_write_failed";return -1;}
      if(record.close_requested)
      {
         if(now-last_request<2) {status="profit_floor_exit_retry_wait";return 0;}
         last_request=now;close_requests++;
         bool sent=broker.PositionClose(ticket);
         if(sent && broker.ResultRetcode()==TRADE_RETCODE_DONE && !PositionSelectByTicket(ticket))
         {status="profit_floor_exit_confirmed";return 2;}
         status="profit_floor_exit_retry_"+(string)broker.ResultRetcode();return 0;
      }
      if(action==PROFIT_HOLD) {status="holding_confirmed_sl";return 0;}
      if(action==PROFIT_BLOCKED) {status="profit_stop_wait_broker_distance";return 0;}
      if(now-last_request<2) {status="profit_stop_retry_wait";return 0;}
      last_request=now;
      bool sent=broker.PositionModify(ticket,NormalizeDouble(desired,_Digits),record.tp);
      uint code=broker.ResultRetcode();
      if(!PositionSelectByTicket(ticket)) {status="position_closed_during_modify";return 0;}
      double observed=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
      if(!sent || (code!=TRADE_RETCODE_DONE && code!=TRADE_RETCODE_NO_CHANGES) ||
         !ProfitStopAccepted(record.direction,record.initial_sl,desired,observed,record.tp,tp,tick))
      {status="profit_stop_unconfirmed_"+(string)code;return 0;}
      record.accepted_sl=observed;
      if(!SaveProfit(path,record)) {status="protection_journal_write_failed";return -1;}
      modifications++;status="profit_stop_confirmed";return 1;
   }
};
#endif

#ifndef GOLDNIX_PROFIT_POLICY
#define GOLDNIX_PROFIT_POLICY
const int PROFIT_HOLD=0,PROFIT_MODIFY=1,PROFIT_EXIT=2,PROFIT_BLOCKED=3,PROFIT_INVALID=4;

bool ProfitStopAccepted(const int direction,const double initial_sl,const double accepted_sl,const double actual_sl,
   const double original_tp,const double actual_tp,const double tick)
{
   return (direction==1 || direction==-1) && MathIsValidNumber(initial_sl) && MathIsValidNumber(accepted_sl) &&
      MathIsValidNumber(actual_sl) && MathIsValidNumber(original_tp) && MathIsValidNumber(actual_tp) &&
      MathIsValidNumber(tick) && tick>0 && initial_sl>0 && accepted_sl>0 && actual_sl>0 && original_tp>0 && actual_tp>0 &&
      direction*(actual_sl-initial_sl)>=-tick*.01 && direction*(actual_sl-accepted_sl)>=-tick*.01 &&
      direction*(original_tp-actual_sl)>0 &&
      MathAbs(actual_tp-original_tp)<=tick*.01;
}

// Prices are executable quote sides. Initial risk never changes with the SL.
int ProfitPlan(const int direction,const double entry,const double initial_sl,const double current_sl,
   const double tp,const double bid,const double ask,const double previous_peak,const double tick,
   const double stop_distance,const double freeze_distance,const double cost_price,double &new_sl,double &peak)
{
   new_sl=current_sl;peak=previous_peak;
   double values[11]={entry,initial_sl,current_sl,tp,bid,ask,previous_peak,tick,stop_distance,freeze_distance,cost_price};
   for(int j=0;j<11;j++) if(!MathIsValidNumber(values[j])) return PROFIT_INVALID;
   if((direction!=1 && direction!=-1) || entry<=0 || initial_sl<=0 || current_sl<=0 || tp<=0 || bid<=0 || ask<bid ||
      tick<=0 || stop_distance<0 || freeze_distance<0 || cost_price<0 || direction*(entry-initial_sl)<=0 ||
      direction*(tp-entry)<=0 || direction*(current_sl-initial_sl)<-tick*.01 || direction*(previous_peak-entry)<-tick*.01)
      return PROFIT_INVALID;
   double quote=direction>0 ? bid : ask,risk=direction*(entry-initial_sl);
   if(direction*(quote-peak)>0) peak=quote;
   double gain=direction*(peak-entry);
   if(gain+tick*1e-6<MathMax(.5*risk,2*cost_price+2*tick)) return PROFIT_HOLD;
   double floor_gain=MathMax(.5*gain,cost_price+tick);
   double level=entry+direction*floor_gain;
   new_sl=direction>0 ? MathCeil(level/tick-1e-8)*tick : MathFloor(level/tick+1e-8)*tick;
   if(direction*(quote-new_sl)<=0) return PROFIT_EXIT;
   if(direction*(new_sl-current_sl)<MathMax(tick,.05*risk)-tick*1e-6) {new_sl=current_sl;return PROFIT_HOLD;}
   double gap=MathMax(stop_distance,freeze_distance)+tick;
   if(direction*(quote-new_sl)<gap || direction*(tp-new_sl)<=0 ||
      (freeze_distance>0 && (direction*(quote-current_sl)<=freeze_distance+tick || direction*(tp-quote)<=freeze_distance+tick)))
      return PROFIT_BLOCKED;
   return PROFIT_MODIFY;
}
#endif

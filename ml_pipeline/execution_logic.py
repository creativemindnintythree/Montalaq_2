class ExecutionLogic:
    @staticmethod
    def generate(entry_price: float, atr: float, signal: str, rr_ratio: float = 2.0):
        """Generate trade execution details based on ML signal and ATR."""

        if atr is None or atr <= 0:
            return {
                'entry_price': entry_price,
                'stop_loss': None,
                'take_profit': None,
                'expected_rr': None
            }

        # Default multipliers
        sl_mult = 1.5  # stop loss distance in ATR
        tp_mult = sl_mult * rr_ratio  # take profit distance in ATR

        if signal == 'LONG':
            stop_loss = entry_price - (atr * sl_mult)
            take_profit = entry_price + (atr * tp_mult)
        elif signal == 'SHORT':
            stop_loss = entry_price + (atr * sl_mult)
            take_profit = entry_price - (atr * tp_mult)
        else:
            stop_loss = None
            take_profit = None

        return {
            'entry_price': entry_price,
            'stop_loss': round(stop_loss, 5) if stop_loss is not None else None,
            'take_profit': round(take_profit, 5) if take_profit is not None else None,
            'expected_rr': rr_ratio
        }

if __name__ == "__main__":
    # Quick test
    logic = ExecutionLogic.generate(entry_price=1.1050, atr=0.0012, signal='LONG')
    print(logic)

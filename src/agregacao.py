"""Agregações de comparecimento e abstenção sobre tabelas com nomes em snake_case."""
import pandas as pd


def taxa_abstencao(df: pd.DataFrame, por: list[str], turno: int = 1) -> pd.DataFrame:
    """Taxa de abstenção (fração 0–1) por grupo, num único turno.

    Filtra `nr_turno == turno` antes de somar: em 2018 e 2022 o mesmo eleitorado aparece
    nos dois turnos, e somar `qt_aptos` entre turnos duplicaria o denominador.
    Grupos com `qt_aptos == 0` recebem taxa NaN (sem divisão por zero).
    """
    turnos = pd.to_numeric(df["nr_turno"], errors="coerce")
    sub = df.loc[turnos == int(turno), por + ["qt_aptos", "qt_abstencao"]]
    r = sub.groupby(por, as_index=False, observed=True)[["qt_aptos", "qt_abstencao"]].sum()
    aptos = r["qt_aptos"].astype("float64")
    r["taxa_abstencao"] = r["qt_abstencao"] / aptos.where(aptos > 0)
    return r[por + ["qt_aptos", "qt_abstencao", "taxa_abstencao"]]

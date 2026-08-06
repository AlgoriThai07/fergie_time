"use client";

import React, { useState } from "react";
import Link from "next/link";

interface PlayerRecommendation {
  player_id: number;
  fpl_id: number;
  name: string;
  team: string;
  position: string;
  price: number;
  xp: number;
}

interface RecommendedLineup {
  starting_xi: PlayerRecommendation[];
  bench: PlayerRecommendation[];
  formation: string;
}

interface RecommendedTransfer {
  transfer_in: PlayerRecommendation;
  transfer_out: PlayerRecommendation;
  xp_gain: number;
}

interface RecommendationsResponse {
  user_id: number;
  gameweek: number;
  bank_balance: number; // in tenths of a million
  lineup: RecommendedLineup;
  transfer: RecommendedTransfer | null;
  xp_map: Record<string, number>;
}

export default function Recommendations() {
  const [fplId, setFplId] = useState<string>("1160158");
  const [gameweek, setGameweek] = useState<string>("2");
  const [apiPort, setApiPort] = useState<string>("8000");
  const [data, setData] = useState<RecommendationsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRecommendations = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fplId.trim() || !gameweek.trim()) return;

    setLoading(true);
    setError(null);
    setData(null);

    const backendUrl = `http://localhost:${apiPort}/recommendations/${fplId}/${gameweek}`;

    try {
      const response = await fetch(backendUrl);
      if (!response.ok) {
        let errMsg = `Error ${response.status}: Failed to fetch recommendations.`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) {
            errMsg = errData.detail;
          }
        } catch {
          // ignore
        }
        throw new Error(errMsg);
      }
      const respData: RecommendationsResponse = await response.json();
      setData(respData);
    } catch (err: any) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const getStartingXIByPosition = (position: string) => {
    if (!data) return [];
    return data.lineup.starting_xi.filter((p) => p.position === position);
  };

  const positions = [
    { code: "GKP", label: "Goalkeepers" },
    { code: "DEF", label: "Defenders" },
    { code: "MID", label: "Midfielders" },
    { code: "FWD", label: "Forwards" },
  ];

  return (
    <main className="min-h-screen bg-slate-50 py-10 px-4 sm:px-6 lg:px-8 text-slate-800">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-extrabold text-slate-900 text-center mb-8">
          FergieTime Optimizer Recommendations
        </h1>

        {/* Navigation Bar */}
        <nav className="bg-white px-6 py-4 rounded-lg shadow-sm border border-slate-200 flex gap-6 mb-8 font-medium text-sm">
          <Link href="/" className="text-slate-500 hover:text-slate-900 transition-colors">
            Squad Viewer
          </Link>
          <Link
            href="/recommendations"
            className="text-blue-600 border-b-2 border-blue-600 pb-0.5 font-bold"
          >
            Recommendations
          </Link>
        </nav>

        {/* Form Inputs */}
        <form
          onSubmit={fetchRecommendations}
          className="bg-white p-6 rounded-lg shadow-sm border border-slate-200 flex flex-wrap gap-4 items-end mb-8"
        >
          <div className="flex-1 min-w-[150px]">
            <label htmlFor="fplId" className="block text-sm font-medium text-slate-700 mb-1">
              FPL Entry ID
            </label>
            <input
              type="text"
              id="fplId"
              value={fplId}
              onChange={(e) => setFplId(e.target.value)}
              placeholder="e.g. 1160158"
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>

          <div className="w-24">
            <label htmlFor="gameweek" className="block text-sm font-medium text-slate-700 mb-1">
              Target GW
            </label>
            <input
              type="number"
              id="gameweek"
              value={gameweek}
              onChange={(e) => setGameweek(e.target.value)}
              placeholder="2"
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>

          <div className="w-24">
            <label htmlFor="apiPort" className="block text-sm font-medium text-slate-700 mb-1">
              API Port
            </label>
            <input
              type="text"
              id="apiPort"
              value={apiPort}
              onChange={(e) => setApiPort(e.target.value)}
              placeholder="8001"
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-blue-400 transition-colors cursor-pointer"
          >
            {loading ? "Optimizing..." : "Get Recommendations"}
          </button>
        </form>

        {/* Error Notification */}
        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-md mb-8">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-red-500" viewBox="0 0 20 20" fill="currentColor">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-red-700 font-medium">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Main display */}
        {data && (
          <div className="space-y-8">
            {/* Suggested Transfer Section */}
            <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
              <div className="bg-slate-900 text-white px-6 py-4 flex justify-between items-center">
                <h2 className="text-xl font-bold">Recommended Transfer Swap</h2>
                <span className="bg-blue-600 px-3 py-1 rounded-full text-xs font-semibold">
                  Gameweek {data.gameweek} Target
                </span>
              </div>

              <div className="p-6">
                {data.transfer ? (
                  <div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center mb-6">
                      {/* Outbound Player */}
                      <div className="p-4 bg-red-50 rounded-lg border border-red-100 flex flex-col justify-between">
                        <span className="text-xs font-bold text-red-800 uppercase tracking-wider mb-2 block">
                          Transfer Out (Sell)
                        </span>
                        <div className="flex justify-between items-center">
                          <div>
                            <span className="text-lg font-bold text-slate-800 block">
                              {data.transfer.transfer_out.name}
                            </span>
                            <span className="text-xs text-slate-500">
                              {data.transfer.transfer_out.team} | {data.transfer.transfer_out.position}
                            </span>
                          </div>
                          <div className="text-right">
                            <span className="text-sm font-bold text-slate-700 block">
                              £{(data.transfer.transfer_out.price / 10).toFixed(1)}m
                            </span>
                            <span className="text-xs font-mono text-red-600 font-semibold bg-red-100/50 px-2 py-0.5 rounded">
                              xP: {data.transfer.transfer_out.xp.toFixed(1)}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Inbound Player */}
                      <div className="p-4 bg-green-50 rounded-lg border border-green-100 flex flex-col justify-between">
                        <span className="text-xs font-bold text-green-800 uppercase tracking-wider mb-2 block">
                          Transfer In (Buy)
                        </span>
                        <div className="flex justify-between items-center">
                          <div>
                            <span className="text-lg font-bold text-slate-800 block">
                              {data.transfer.transfer_in.name}
                            </span>
                            <span className="text-xs text-slate-500">
                              {data.transfer.transfer_in.team} | {data.transfer.transfer_in.position}
                            </span>
                          </div>
                          <div className="text-right">
                            <span className="text-sm font-bold text-slate-700 block">
                              £{(data.transfer.transfer_in.price / 10).toFixed(1)}m
                            </span>
                            <span className="text-xs font-mono text-green-600 font-semibold bg-green-100/50 px-2 py-0.5 rounded">
                              xP: {data.transfer.transfer_in.xp.toFixed(1)}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Financial details & xP profit summary */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-slate-50 rounded-lg border border-slate-200">
                      <div>
                        <span className="text-xs text-slate-500 block">xP Gain</span>
                        <span className="text-lg font-bold text-blue-600">
                          +{data.transfer.xp_gain.toFixed(2)} pts
                        </span>
                      </div>
                      <div>
                        <span className="text-xs text-slate-500 block">Transfer Cost</span>
                        <span className="text-lg font-bold text-slate-800">
                          £{((data.transfer.transfer_in.price - data.transfer.transfer_out.price) / 10).toFixed(1)}m
                        </span>
                      </div>
                      <div>
                        <span className="text-xs text-slate-500 block">Bank Before</span>
                        <span className="text-lg font-bold text-slate-800">
                          £{(data.bank_balance / 10).toFixed(1)}m
                        </span>
                      </div>
                      <div>
                        <span className="text-xs text-slate-500 block">Bank After</span>
                        <span className="text-lg font-bold text-slate-800">
                          £{((data.bank_balance - (data.transfer.transfer_in.price - data.transfer.transfer_out.price)) / 10).toFixed(1)}m
                        </span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-6 text-slate-500 bg-slate-50 border border-dashed border-slate-200 rounded-lg">
                    No beneficial transfers found within budget constraint. (Raw xP gain is ≤ 0)
                  </div>
                )}
              </div>
            </div>

            {/* Recommended Lineup Section */}
            <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
              <div className="bg-slate-900 text-white px-6 py-4 flex justify-between items-center">
                <div>
                  <h2 className="text-xl font-bold">Recommended Starting XI</h2>
                  <p className="text-xs text-slate-400">Optimized for maximum expected points</p>
                </div>
                <span className="bg-green-600 px-3 py-1 rounded-full text-xs font-semibold">
                  Formation: {data.lineup.formation}
                </span>
              </div>

              <div className="p-6 space-y-8">
                {positions.map((pos) => {
                  const starters = getStartingXIByPosition(pos.code);
                  if (starters.length === 0) return null;

                  return (
                    <div key={pos.code}>
                      <h3 className="text-lg font-semibold text-slate-900 border-b border-slate-200 pb-2 mb-4">
                        {pos.label}
                      </h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {starters.map((player) => (
                          <div
                            key={player.player_id}
                            className="flex items-center justify-between p-4 border border-slate-100 rounded-lg hover:bg-slate-50 transition-colors"
                          >
                            <div>
                              <span className="font-semibold text-slate-800 block">
                                {player.name}
                              </span>
                              <span className="text-xs text-slate-500">
                                Team: <span className="font-medium text-slate-700">{player.team}</span> | Price:{" "}
                                <span className="font-medium text-slate-700">
                                  £{(player.price / 10).toFixed(1)}m
                                </span>
                              </span>
                            </div>
                            <span className="bg-blue-100 text-blue-800 text-xs font-bold px-3 py-1 rounded border border-blue-200 font-mono">
                              xP: {player.xp.toFixed(1)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Bench Order Section */}
            <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
              <div className="bg-slate-900 text-white px-6 py-4">
                <h2 className="text-xl font-bold">Recommended Bench Order</h2>
                <p className="text-xs text-slate-400">GK first, then outfield players ordered worst to best xP</p>
              </div>

              <div className="p-6">
                <div className="space-y-3">
                  {data.lineup.bench.map((player, index) => (
                    <div
                      key={player.player_id}
                      className="flex items-center justify-between p-4 border border-slate-100 rounded-lg bg-slate-50/50 hover:bg-slate-50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <span className="w-6 h-6 bg-slate-200 text-slate-700 text-xs font-bold flex items-center justify-center rounded-full">
                          {index + 1}
                        </span>
                        <div>
                          <span className="font-semibold text-slate-800 block">
                            {player.name}
                          </span>
                          <span className="text-xs text-slate-500">
                            Team: <span className="font-medium text-slate-700">{player.team}</span> | Pos:{" "}
                            <span className="font-medium text-slate-700">{player.position}</span> | Price:{" "}
                            <span className="font-medium text-slate-700">
                              £{(player.price / 10).toFixed(1)}m
                            </span>
                          </span>
                        </div>
                      </div>
                      <span className="bg-slate-200 text-slate-700 text-xs font-bold px-3 py-1 rounded border border-slate-300 font-mono">
                        xP: {player.xp.toFixed(1)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {!data && !loading && !error && (
          <div className="text-center py-12 text-slate-400 border-2 border-dashed border-slate-200 rounded-lg bg-white">
            Enter an FPL Entry ID, Target GW, and click "Get Recommendations" to run the ILP Optimizer.
          </div>
        )}
      </div>
    </main>
  );
}

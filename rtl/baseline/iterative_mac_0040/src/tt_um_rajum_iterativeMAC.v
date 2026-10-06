`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: Raju Machupalli
// 
// Create Date: 06/01/2024 08:21:00 AM
// Design Name: 
// Module Name: tt_rajum_iterativeMAC
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////

/*
 * Copyright (c) 2024 Your Name
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_rajum_iterativeMAC (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it.
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);
  //make all the uio pins as output

  reg mode; //defines the mode of operation, for inference mode = 0, for training mode = 1
  reg [6:0] inp_a; // To store the input activation
  reg [31:0] sum, result; // to store bias and multiplication results
  reg [2:0] state; //fsm state
  wire out_th;
  reg [31:0] temp_b;
  wire [31:0] temp_a, temp_c;


  assign uio_oe = mode?8'b0000_0000:8'b1111_1111;
  assign uio_out = mode?8'bxx:result[23:16];
  assign uo_out = result[31:24];
  
  wire [14:0] out;
  
  // instatiate multiplier 
  multi mu (inp_a, ui_in, out);
  
  assign out_th = |out[14:11];
  //always @(*) begin
  //  out_th = out[14] | out[13] | out[12] | out[11];
  //end

  adder ad (temp_a, temp_b, temp_c);

//FSM for iterative operation
always @(posedge clk)
	begin
	if (rst_n == 1'b0) begin
	  mode <= ui_in[7];
	  inp_a <= ui_in[6:0];
	  result <= 32'd0;
	  sum <= 32'd0;
	  state <= 3'b000;
	end
	else begin 
	  case (state)
	  3'b000: begin 
	    state <= state + 1;
	    result[31:16] <= out;
	    end
	  3'b001: begin
	    sum <= temp_c;
	    result <= result << 8;
	    if (mode == 1'b0) state <= state;
	    else begin 
	      if (out_th == 1'b1) state<= 3'b101;
	      else state <= state + 1;
	    end
	  end
	  3'b010: begin
	    sum <= temp_c;
	    result <= result << 8;
	    if (out_th == 1'b1) state<= 3'b110;
	    else state <= state + 1;
	  end
	  3'b011: begin
	    sum <= temp_c;
	    result <= result << 8;
	    if (out_th == 1'b1) state<= 3'b111;
	    else state <= state + 1;
	  end
	  3'b100: begin
	    sum <= 0;
	    result <= temp_c;
	    state<= 3'b001;
	  end
	  3'b111: begin
	    sum <= 0;
	    result <= temp_c;
	    state<= 3'b001;
	  end
	  default: begin
	    state <= state + 1;
	    sum <= temp_c;
	    result <= result << 8;
	  end
	  endcase
	end
      end

always @(*)
begin
	case (state)
	3'b000: temp_b = 0;
	3'b001: temp_b = {1'b0, out, uio_in, 8'd0}; // adding the second LSB byte from bias
	3'b010: temp_b = {9'b0, out, uio_in}; 
	3'b011: temp_b = {uio_in, 9'd0, out};
	3'b100: temp_b = {8'd0, uio_in, 9'd0, out[14:8]};
	3'b101: temp_b = {9'b0, out, uio_in};
	3'b110: temp_b = {uio_in, 9'd0, out};
	3'b111: temp_b = {8'd0, uio_in, 9'd0, out[14:8]};
//	3'b000: temp_b = {1'b0, out, uio_in, 8'd0}; // adding the second LSB byte from bias
//	3'b001: temp_b = {9'b0, out, uio_in}; 
//	3'b010: temp_b = {uio_in, 9'd0, out};
//	3'b011: temp_b = {8'd0, uio_in, 9'd0, out[14:8]};
//	3'b100: temp_b = {1'b0, out, uio_in, 8'd0};
//	3'b101: temp_b = {9'b0, out, uio_in};
//	3'b110: temp_b = {uio_in, 9'd0, out};
//	3'b111: temp_b = {8'd0, uio_in, 9'd0, out[14:8]};
	endcase
end

assign temp_a = sum;
  
  // List all unused inputs to prevent warnings
  wire _unused = &{ena, 1'b0};

endmodule



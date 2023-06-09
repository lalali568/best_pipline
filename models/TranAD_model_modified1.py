import torch
from torch.nn import TransformerDecoder,TransformerEncoder
import torch.nn as nn
import math

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, dropout=0.1, max_len=5000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model).float() * (-math.log(10000.0) / d_model))
        pe += torch.sin(position * div_term)
        pe += torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer('pe', pe)#

    def forward(self, x, pos=0):
        x = x + self.pe[pos:pos+x.size(0), :]
        return self.dropout(x)

class TransformerEncoderLayer(nn.Module):
    def __init__(self, config,d_model, nhead, dim_feedforward=16, dropout=0):
        super(TransformerEncoderLayer, self).__init__()
        self.self_attn = nn.MultiheadAttention(d_model, nhead, dropout=dropout)
        self.linear1 = nn.Linear(d_model, dim_feedforward)
        self.dropout = nn.Dropout(dropout)
        self.linear2 = nn.Linear(dim_feedforward, d_model)
        self.dropout1 = nn.Dropout(dropout)
        self.dropout2 = nn.Dropout(dropout)
        self.config=config
        self.activation = nn.LeakyReLU(True)


    def forward(self, tgt,src_mask=None,is_causal=None, src_key_padding_mask=None):
        tgt2=self.self_attn(tgt,tgt,tgt)[0]
        batchnorm=nn.BatchNorm1d(tgt.shape[1]).to(self.config['device'])
        tgt= batchnorm(tgt+self.dropout1(tgt2))
        tgt2=self.linear2(self.dropout(self.activation(self.linear1(tgt))))
        tgt= batchnorm(tgt+self.dropout2(tgt2))
        return tgt

        """
        src2 = self.self_attn(src, src, src)[0]
        batchnorm=nn.BatchNorm1d(src.shape[1])
        src = batchnorm(src + self.dropout1(src2))
        src2 = self.linear2(self.dropout(self.activation(self.linear1(src))))
        src = batchnorm(src + self.dropout2(src2))
        return src
        """

class TransformerDecoderLayer(nn.Module):
    def __init__(self, config,d_model, nhead, dim_feedforward=16, dropout=0):#d_model是feat*2.nhead就是feat数
        super(TransformerDecoderLayer, self).__init__()
        self.self_attn = nn.MultiheadAttention(d_model, nhead, dropout=dropout)
        self.multihead_attn = nn.MultiheadAttention(d_model, nhead, dropout=dropout)
        self.linear1 = nn.Linear(d_model, dim_feedforward)
        self.dropout = nn.Dropout(dropout)
        self.linear2 = nn.Linear(dim_feedforward, d_model)
        self.dropout1 = nn.Dropout(dropout)
        self.dropout2 = nn.Dropout(dropout)
        self.dropout3 = nn.Dropout(dropout)
        self.pos_encoder = PositionalEncoding(config['feat']*2,0.1,config['window_size'])
        self.activation = nn.LeakyReLU(True)
        self.sigmoid = nn.Sigmoid()
        self.config=config

    def create_mask(self,size):
        mask = torch.triu(torch.ones(size, size), diagonal=1)
        mask = mask == 0
        return mask

    def forward(self, src, memory, tgt_mask=None, memory_mask=None, tgt_key_padding_mask=None, memory_key_padding_mask=None):

        src = self.pos_encoder(src)
        #mask = self.create_mask(src.shape[0]).to(self.config['device'])
        #src2 = self.self_attn(src, src, src,attn_mask=mask)[0]
        src2 = self.self_attn(src, src, src)[0]
        batchnorm= nn.BatchNorm1d(src.shape[1]).to(self.config['device'])
        src =batchnorm(src + self.dropout1(src2))
        src2 = self.multihead_attn(memory, src,src)[0]
        src =  self.dropout2(src2)#感觉这里和下面的直接接上有点奇怪
        #src2 = self.linear2(self.dropout(self.activation(self.linear1(src))))
        #src = batchnorm(src+self.dropout3(src2))
        return src
class TranAD(nn.Module):
    def __init__(self,config):
        super(TranAD, self).__init__()
        self.lr = config['learn_rate']
        self.n_feats = config['feat']
        self.n_window = config['window_size']
        self.n = self.n_feats * self.n_window
        self.nhead = config['nhead']
        self.dim_feedforward = config['dim_feedforward']
        self.pos_encoder = PositionalEncoding(2*self.n_feats,0.1,self.n_window)
        encoder_layers = TransformerEncoderLayer(config,d_model=2* self.n_feats, nhead=self.nhead, dim_feedforward=self.dim_feedforward, dropout=config['dropout'])  # 这里是定义一个encoder_layer
        self.transformer_encoder = TransformerEncoder(encoder_layers, 1)
        decoder_layers1 = TransformerDecoderLayer(config,d_model=2* self.n_feats, nhead=self.nhead, dim_feedforward=self.dim_feedforward, dropout=config['dropout'])
        self.transformer_decoder1 = TransformerDecoder(decoder_layers1, 1)
        decoder_layers2 = TransformerDecoderLayer(config,d_model= 2*self.n_feats, nhead=self.nhead, dim_feedforward=self.dim_feedforward, dropout=config['dropout'])
        self.transformer_decoder2 = TransformerDecoder(decoder_layers2, 1)
        self.fcn = nn.Sequential(nn.Linear(2*self.n_feats, self.n_feats), nn.Sigmoid())


    def encode(self, src, c, tgt):
        """这是本来的代码
        src = torch.cat((src, c), dim=2)
        src = src * math.sqrt(self.n_feats)
        src = self.pos_encoder(src)
        memory = self.transformer_encoder(src)
        tgt = tgt.repeat(1, 1, 2)  #这里为啥要repeat
        return tgt, memory
        """
        tgt = torch.cat((tgt, c), dim=2)
        #tgt=tgt*c#我试一下把c作为强调指标加到里面
        tgt = tgt * math.sqrt(self.n_feats)
        tgt = self.pos_encoder(tgt)
        memory = self.transformer_encoder(tgt)
        src = src.repeat(1, 1, 2)
        return src, memory


    def forward(self, src, tgt):#src是切出来的，tat是整个dataloader的时序
        # Phase 1 - Without anomaly scores
        #c = torch.zeros_like(tgt)
        c=torch.zeros_like(tgt)

        x1 = self.fcn(self.transformer_decoder1(*self.encode(src, c, tgt))) #这个是原始的
        # Phase 2 - With anomaly scores
        c = (x1 - tgt) ** 2#我感觉这里也不太一样，x1是对整个batch的数据进行重构的，但是为啥这里是和src进行相减呢
        x2 = self.fcn(self.transformer_decoder2(*self.encode(src, c, tgt)))
        return x1, x2

